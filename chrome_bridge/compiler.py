"""Deep DOM Compiler module for batch JavaScript synthesis, fluent discovery, and structured error decoding."""

import json
import time
from typing import Any, Callable, Dict, List, Optional, Union

from .exceptions import (
    ActionInterceptionError,
    ChromeBridgeError,
    ElementNotFoundError,
    NavigationTimeoutError,
    TargetLocator,
    _extract_hostname,
    normalize_locator,
)

_DISCOVERY_HELPER_JS = """
function __cb_is_visible(el, style) {
    if (!el || el.nodeType !== 1) return false;
    if (el.hasAttribute('hidden') || el.getAttribute('aria-hidden') === 'true' || el.hasAttribute('inert')) return false;
    if (typeof el.checkVisibility === 'function') {
        if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) {
            if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) return true;
            return false;
        }
    }
    if (!style) style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse' || parseFloat(style.opacity) < 0.05) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
        if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) return true;
        return false;
    }
    return true;
}

function __cb_get_accessible_name(el) {
    if (!el) return '';
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
        const parts = labelledby.split(/\\s+/).map(id => document.getElementById(id)?.innerText?.trim()).filter(Boolean);
        if (parts.length > 0) return parts.join(' ');
    }
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

    if (el.id && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) {
        try {
            const labelEl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
            if (labelEl && labelEl.innerText.trim()) return labelEl.innerText.trim();
        } catch(e) {}
    }
    const parentLabel = el.closest('label');
    if (parentLabel && parentLabel.innerText.trim()) return parentLabel.innerText.trim();

    if (el.getAttribute('placeholder')) return el.getAttribute('placeholder').trim();
    if (el.getAttribute('title')) return el.getAttribute('title').trim();
    if (el.getAttribute('alt')) return el.getAttribute('alt').trim();

    if (['BUTTON', 'A', 'SUMMARY', 'OPTION'].includes(el.tagName)) {
        const fullText = (el.innerText || el.textContent || '').trim();
        if (fullText) return fullText.slice(0, 120);
    }
    return (el.innerText || el.textContent || el.value || '').trim().slice(0, 120);
}

function __cb_get_computed_role(el) {
    if (!el) return 'generic';
    const explicitRole = el.getAttribute('role');
    if (explicitRole) return explicitRole.toLowerCase().trim();

    const tag = el.tagName.toLowerCase();
    switch (tag) {
        case 'a': return el.hasAttribute('href') ? 'link' : 'generic';
        case 'button': return 'button';
        case 'input': {
            const type = (el.getAttribute('type') || 'text').toLowerCase();
            if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
            if (type === 'checkbox') return 'checkbox';
            if (type === 'radio') return 'radio';
            if (type === 'search') return 'searchbox';
            return 'textbox';
        }
        case 'select': return 'combobox';
        case 'textarea': return 'textbox';
        case 'summary': return 'button';
        case 'details': return 'group';
        case 'h1': return 'heading[level=1]';
        case 'h2': return 'heading[level=2]';
        case 'h3': return 'heading[level=3]';
        case 'h4': return 'heading[level=4]';
        case 'h5': return 'heading[level=5]';
        case 'h6': return 'heading[level=6]';
        case 'nav': return 'navigation';
        case 'main': return 'main';
        case 'header': return 'banner';
        case 'footer': return 'contentinfo';
        case 'form': return 'form';
        case 'table': return 'table';
        default: return 'generic';
    }
}

function __cb_tag(el) {
    if (!el) return null;
    if (!window.__cb_handle_counter) window.__cb_handle_counter = 0;
    let bridgeId = el.getAttribute('data-cbridge-id');
    if (!bridgeId) {
        bridgeId = 'cb_' + (++window.__cb_handle_counter) + '_' + Date.now().toString(36);
        el.setAttribute('data-cbridge-id', bridgeId);
    }
    const text = __cb_get_accessible_name(el);
    const role = __cb_get_computed_role(el);
    return {
        selector: '[data-cbridge-id="' + bridgeId + '"]',
        tagName: el.tagName.toLowerCase(),
        role: role,
        text: text.slice(0, 100),
        id: el.id || '',
        name: el.getAttribute('name') || '',
        placeholder: el.getAttribute('placeholder') || '',
        value: el.value || ''
    };
}

function __cb_wait_for(finderFn, timeoutMs) {
    timeoutMs = (typeof timeoutMs === 'number') ? timeoutMs : 1500;
    try {
        const immediate = finderFn();
        if (immediate) return Promise.resolve(immediate);
    } catch(e) {}
    if (timeoutMs <= 0) return Promise.resolve(null);

    return new Promise((resolve) => {
        let timer = null;
        let observer = null;
        let rafId = null;

        const cleanup = () => {
            if (timer) clearTimeout(timer);
            if (observer) observer.disconnect();
            if (rafId && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(rafId);
        };

        const check = () => {
            try {
                const found = finderFn();
                if (found) {
                    cleanup();
                    resolve(found);
                    return true;
                }
            } catch(e) {}
            return false;
        };

        try {
            if (typeof MutationObserver !== 'undefined') {
                observer = new MutationObserver(() => {
                    check();
                });
                const root = document.documentElement || document.body;
                if (root) {
                    observer.observe(root, {
                        childList: true,
                        subtree: true,
                        attributes: true,
                        characterData: true
                    });
                }
            }
        } catch(e) {}

        if (typeof requestAnimationFrame === 'function') {
            const loop = () => {
                if (!check()) {
                    rafId = requestAnimationFrame(loop);
                }
            };
            rafId = requestAnimationFrame(loop);
        }

        timer = setTimeout(() => {
            cleanup();
            try {
                resolve(finderFn());
            } catch(e) {
                resolve(null);
            }
        }, timeoutMs);
    });
}
"""


class DomCompiler:
    """Pure compiler and execution dispatch module for in-page compound batch operations and DOM discovery.

    Translates high-level batch intents (element finding heuristics, structured data extraction,
    form filling, and search engine shortcuts) into optimized single-pass JavaScript payloads,
    and decodes structured responses and Diagnostic Reports into domain exceptions.
    """

    SEARCH_ENGINES: Dict[str, str] = {
        "google": "https://www.google.com/search?q={query}",
        "g": "https://www.google.com/search?q={query}",
        "bing": "https://www.bing.com/search?q={query}",
        "b": "https://www.bing.com/search?q={query}",
        "duckduckgo": "https://duckduckgo.com/?q={query}",
        "ddg": "https://duckduckgo.com/?q={query}",
        "youtube": "https://www.youtube.com/results?search_query={query}",
        "yt": "https://www.youtube.com/results?search_query={query}",
        "github": "https://github.com/search?q={query}",
        "gh": "https://github.com/search?q={query}",
    }

    @classmethod
    def compile_search_url(cls, query: str, engine: str = "google") -> str:
        """Resolve target search engine URL for a given query string."""
        import urllib.parse
        q_enc = urllib.parse.quote_plus(query)
        eng_lower = engine.lower().strip()
        if eng_lower in cls.SEARCH_ENGINES:
            return cls.SEARCH_ENGINES[eng_lower].format(query=q_enc)
        elif "{query}" in engine:
            return engine.replace("{query}", q_enc)
        elif engine.startswith("http://") or engine.startswith("https://"):
            return f"{engine}?q={q_enc}" if "?" not in engine else f"{engine}&q={q_enc}"
        else:
            return f"https://www.google.com/search?q={q_enc}"

    @classmethod
    def compile_find_element_rpc(
        cls,
        query: Union[str, int, TargetLocator],
        strategy: str = "polymorphic",
        exact: bool = False,
        timeout: float = 1.5,
        **extra_params: Any,
    ) -> Dict[str, Any]:
        """Compile structured find_element Action RPC payload."""
        norm_query = query
        if isinstance(query, (int, dict)):
            norm_query = normalize_locator(query)
        params = {
            "query": norm_query,
            "strategy": strategy,
            "exact": exact,
            "timeout": timeout,
        }
        params.update(extra_params)
        return {
            "action": "find_element",
            "params": params,
        }

    @classmethod
    def compile_query_elements_rpc(
        cls,
        selector: str,
        **extra_params: Any,
    ) -> Dict[str, Any]:
        """Compile structured query_elements Action RPC payload."""
        params = {
            "selector": selector,
        }
        params.update(extra_params)
        return {
            "action": "query_elements",
            "params": params,
        }

    @classmethod
    def compile_extract_items_rpc(
        cls,
        container_selector: str,
        fields: Dict[str, str],
        **extra_params: Any,
    ) -> Dict[str, Any]:
        """Compile structured extract_items Action RPC payload."""
        params = {
            "item_selector": container_selector,
            "fields": fields,
        }
        params.update(extra_params)
        return {
            "action": "extract_items",
            "params": params,
        }

    @classmethod
    def compile_fill_form_rpc(
        cls,
        mapping: Dict[str, Any],
        submit: Optional[Union[str, bool]] = None,
        **extra_params: Any,
    ) -> Dict[str, Any]:
        """Compile structured fill_form Action RPC payload."""
        params = {
            "mapping": mapping,
            "submit": submit,
        }
        params.update(extra_params)
        return {
            "action": "fill_form",
            "params": params,
        }

    @classmethod
    def compile_action_rpc(cls, action: str, **params: Any) -> Dict[str, Any]:
        """Validate and compile structured Action RPC payload for extension coordinator dispatch."""
        compiled_params = dict(params)
        loc = compiled_params.get("target")
        if loc is not None:
            compiled_params["target"] = normalize_locator(loc)
        return {
            "action": action,
            "params": compiled_params,
        }


    @classmethod
    def compile_media_control(cls, action: str, **kwargs: Any) -> str:
        """Generate fast-path JavaScript for HTML5 media and MediaSession control."""
        find_js = """
        function findMediaElement(root = document) {
            let el = root.querySelector('video, audio');
            if (el) return el;
            const all = root.querySelectorAll('*');
            for (const node of all) {
                if (node.shadowRoot) {
                    const nested = findMediaElement(node.shadowRoot);
                    if (nested) return nested;
                }
            }
            return null;
        }
        """
        if action == "status":
            return f"""
            (() => {{
                {find_js}
                const media = findMediaElement();
                const session = navigator.mediaSession;
                return {{
                    found: !!media,
                    paused: media ? media.paused : null,
                    currentTime: media ? media.currentTime : null,
                    duration: media ? media.duration : null,
                    volume: media ? media.volume : null,
                    muted: media ? media.muted : null,
                    title: session?.metadata?.title || document.title,
                    artist: session?.metadata?.artist || "",
                    album: session?.metadata?.album || "",
                    playbackState: session?.playbackState || (media ? (media.paused ? "paused" : "playing") : "none")
                }};
            }})()
            """
        elif action == "toggle":
            return f"""
            (() => {{
                {find_js}
                const media = findMediaElement();
                if (!media) return {{success: false, error: "No media element found"}};
                if (media.paused) {{
                    media.play();
                    return {{success: true, action: "played"}};
                }} else {{
                    media.pause();
                    return {{success: true, action: "paused"}};
                }}
            }})()
            """
        elif action == "play":
            return f"""
            (() => {{
                {find_js}
                const v = findMediaElement();
                if (v) {{ v.play(); return {{success: true}}; }}
                return {{success: false, error: "No media element found"}};
            }})()
            """
        elif action == "pause":
            return f"""
            (() => {{
                {find_js}
                const v = findMediaElement();
                if (v) {{ v.pause(); return {{success: true}}; }}
                return {{success: false, error: "No media element found"}};
            }})()
            """
        elif action == "seek":
            sec = float(kwargs.get("seconds", 0.0))
            return f"""
            (() => {{
                {find_js}
                const v = findMediaElement();
                if (!v) return {{success: false, error: "No media element found"}};
                v.currentTime += {sec};
                return {{success: true, currentTime: v.currentTime}};
            }})()
            """
        elif action == "set_volume":
            vol = max(0.0, min(1.0, float(kwargs.get("volume", 1.0))))
            return f"""
            (() => {{
                {find_js}
                const v = findMediaElement();
                if (v) {{ v.volume = {vol}; v.muted = false; return {{success: true, volume: v.volume}}; }}
                return {{success: false, error: "No media element found"}};
            }})()
            """
        return "(() => ({}))()"

    @classmethod
    def compile_extract_items_js(cls, container_selector: str, fields: Dict[str, str]) -> str:
        """Generate JavaScript payload for structured multi-field extraction across container elements."""
        return f"""
        (() => {{
            const containerSelector = {json.dumps(container_selector)};
            const fields = {json.dumps(fields)};
            const containers = Array.from(document.querySelectorAll(containerSelector));
            const results = [];

            for (const container of containers) {{
                const row = {{}};
                for (const [key, fieldSel] of Object.entries(fields)) {{
                    let targetEl = container;
                    let attrName = null;
                    let sel = (fieldSel || '').trim();

                    if (sel.includes('@')) {{
                        const parts = sel.split('@');
                        const subSel = parts[0].trim();
                        attrName = parts[1].trim();
                        if (subSel && subSel !== '.' && subSel !== 'self' && subSel.toLowerCase() !== 'text') {{
                            targetEl = container.querySelector(subSel);
                        }}
                    }} else if (sel && sel !== '.' && sel !== 'self' && sel.toLowerCase() !== 'text') {{
                        targetEl = container.querySelector(sel);
                    }}

                    if (!targetEl) {{
                        row[key] = "";
                    }} else if (attrName) {{
                        if (attrName.toLowerCase() === 'text') {{
                            row[key] = (targetEl.innerText || targetEl.textContent || "").trim();
                        }} else {{
                            const val = targetEl.getAttribute(attrName);
                            row[key] = (val !== null && val !== undefined ? val : "").toString().trim();
                        }}
                    }} else {{
                        row[key] = (targetEl.innerText || targetEl.textContent || "").trim();
                    }}
                }}
                results.push(row);
            }}
            return results;
        }})()
        """

    @classmethod
    def compile_query_all_js(cls, css_selector: str) -> str:
        """Generate JavaScript payload for finding and tagging all visible elements matching a CSS selector."""
        return f"""
        (() => {{
            {_DISCOVERY_HELPER_JS}
            const selector = {json.dumps(css_selector)};
            const all = document.querySelectorAll(selector);
            const results = [];
            for (const el of all) {{
                if (__cb_is_visible(el)) {{
                    const tagged = __cb_tag(el);
                    if (tagged) results.push(tagged);
                }}
            }}
            return results;
        }})()
        """

    @classmethod
    def compile_find_css_js(cls, target_str: str, timeout: float = 1.5) -> str:
        """Generate JavaScript payload for locating a visible element by CSS selector with in-page synchronizer."""
        timeout_ms = int((timeout or 1.5) * 1000)
        return f"""
        (async () => {{
            {_DISCOVERY_HELPER_JS}
            return await __cb_wait_for(() => {{
                try {{
                    const el = document.querySelector({json.dumps(target_str)});
                    if (el && __cb_is_visible(el)) return __cb_tag(el);
                }} catch (e) {{}}
                return null;
            }}, {timeout_ms});
        }})()
        """

    @classmethod
    def compile_text_finder_js(cls, text: str, exact: bool = False, timeout: float = 1.5) -> str:
        """Generate JavaScript payload for finding a visible element by inner or accessible text with in-page synchronizer."""
        timeout_ms = int((timeout or 1.5) * 1000)
        return f"""
        (async () => {{
            {_DISCOVERY_HELPER_JS}
            const query = {json.dumps(text)};
            const exact = {json.dumps(exact)};
            const qLower = query.toLowerCase();

            return await __cb_wait_for(() => {{
                const candidates = [];
                const all = document.querySelectorAll('button, a, input, [role], p, span, h1, h2, h3, h4, h5, h6, li, td, th, label, div');
                for (const el of all) {{
                    if (!__cb_is_visible(el)) continue;
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (!txt) continue;
                    const tLower = txt.toLowerCase();
                    
                    let match = false;
                    let score = 0;
                    if (exact) {{
                        if (tLower === qLower) {{ match = true; score = 100; }}
                    }} else {{
                        if (tLower === qLower) {{ match = true; score = 100; }}
                        else if (tLower.includes(qLower)) {{ match = true; score = 50 + Math.max(0, 40 - (txt.length - query.length)); }}
                    }}

                    if (match) {{
                        const isInteractive = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA', 'LABEL'].includes(el.tagName) || el.hasAttribute('role');
                        if (isInteractive) score += 30;
                        score -= Math.min(20, el.children.length * 5);
                        candidates.push({{ el, score }});
                    }}
                }}

                if (candidates.length === 0) return null;
                candidates.sort((a, b) => b.score - a.score);
                return __cb_tag(candidates[0].el);
            }}, {timeout_ms});
        }})()
        """

    @classmethod
    def compile_input_finder_js(cls, placeholder_or_label: str, timeout: float = 1.5) -> str:
        """Generate JavaScript payload for finding an input, textarea, or select by placeholder, label, or name with in-page synchronizer."""
        timeout_ms = int((timeout or 1.5) * 1000)
        return f"""
        (async () => {{
            {_DISCOVERY_HELPER_JS}
            const query = {json.dumps(placeholder_or_label)};
            const qLower = query.toLowerCase();

            return await __cb_wait_for(() => {{
                const inputs = document.querySelectorAll('input:not([type="hidden"]), textarea, select, [contenteditable="true"], [role="textbox"], [role="searchbox"], [role="combobox"]');
                const candidates = [];

                for (const el of inputs) {{
                    if (!__cb_is_visible(el)) continue;
                    let score = 0;

                    const placeholder = (el.getAttribute('placeholder') || '').trim().toLowerCase();
                    if (placeholder === qLower) score = 100;
                    else if (placeholder.includes(qLower)) score = 80;

                    const ariaLabel = (el.getAttribute('aria-label') || el.getAttribute('aria-placeholder') || '').trim().toLowerCase();
                    if (ariaLabel === qLower) score = Math.max(score, 95);
                    else if (ariaLabel.includes(qLower)) score = Math.max(score, 75);

                    const name = (el.getAttribute('name') || '').trim().toLowerCase();
                    const id = (el.id || '').trim().toLowerCase();
                    if (name === qLower || id === qLower) score = Math.max(score, 90);
                    else if (name.includes(qLower) || id.includes(qLower)) score = Math.max(score, 70);

                    if (el.id) {{
                        try {{
                            const labelEl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                            if (labelEl) {{
                                const lText = labelEl.innerText.trim().toLowerCase();
                                if (lText === qLower) score = Math.max(score, 95);
                                else if (lText.includes(qLower)) score = Math.max(score, 75);
                            }}
                        }} catch (e) {{}}
                    }}
                    const parentLabel = el.closest('label');
                    if (parentLabel) {{
                        const lText = parentLabel.innerText.trim().toLowerCase();
                        if (lText === qLower) score = Math.max(score, 90);
                        else if (lText.includes(qLower)) score = Math.max(score, 70);
                    }}

                    if (score > 0) {{
                        candidates.push({{ el, score }});
                    }}
                }}

                if (candidates.length === 0) return null;
                candidates.sort((a, b) => b.score - a.score);
                return __cb_tag(candidates[0].el);
            }}, {timeout_ms});
        }})()
        """

    @classmethod
    def compile_button_finder_js(cls, name: str, exact: bool = False, timeout: float = 1.5) -> str:
        """Generate JavaScript payload for finding a button or clickable role by visible name with in-page synchronizer."""
        timeout_ms = int((timeout or 1.5) * 1000)
        return f"""
        (async () => {{
            {_DISCOVERY_HELPER_JS}
            const query = {json.dumps(name)};
            const exact = {json.dumps(exact)};
            const qLower = query.toLowerCase();

            return await __cb_wait_for(() => {{
                const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"], input[type="reset"], [role="button"], a.btn, a.button, a[role="button"], summary, a');
                const candidates = [];

                for (const el of buttons) {{
                    if (!__cb_is_visible(el)) continue;
                    const txt = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                    if (!txt) continue;
                    const tLower = txt.toLowerCase();

                    let score = 0;
                    if (exact) {{
                        if (tLower === qLower) score = 100;
                    }} else {{
                        if (tLower === qLower) score = 100;
                        else if (tLower.includes(qLower)) score = 50 + Math.max(0, 40 - (txt.length - query.length));
                    }}

                    if (score > 0) {{
                        if (el.tagName === 'BUTTON' || (el.tagName === 'INPUT' && el.type === 'submit')) score += 20;
                        candidates.push({{ el, score }});
                    }}
                }}

                if (candidates.length === 0) return null;
                candidates.sort((a, b) => b.score - a.score);
                return __cb_tag(candidates[0].el);
            }}, {timeout_ms});
        }})()
        """

    @classmethod
    def compile_fill_form_js(cls, mapping: Dict[str, Any], submit: Optional[Union[str, bool]] = None) -> str:
        """Generate single-roundtrip JavaScript payload to fill an entire form and optionally submit."""
        return f"""
        (() => {{
            {_DISCOVERY_HELPER_JS}
            const mapping = {json.dumps(mapping)};
            const submit = {json.dumps(submit)};
            let filledCount = 0;
            const errors = [];

            function findField(key) {{
                if (key.startsWith('[#') || key.startsWith('#') || key.startsWith('.') || key.startsWith('input') || key.startsWith('[data-')) {{
                    try {{
                        const el = document.querySelector(key);
                        if (el && __cb_is_visible(el)) return el;
                    }} catch(e) {{}}
                }}
                const qLower = key.toLowerCase();
                const inputs = document.querySelectorAll('input:not([type="hidden"]), textarea, select, [contenteditable="true"], [role="textbox"], [role="searchbox"], [role="combobox"]');
                let best = null;
                let bestScore = 0;
                for (const el of inputs) {{
                    if (!__cb_is_visible(el)) continue;
                    let score = 0;
                    const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const nm = (el.getAttribute('name') || '').toLowerCase();
                    const id = (el.id || '').toLowerCase();
                    if (ph === qLower || aria === qLower || nm === qLower || id === qLower) score = 100;
                    else if (ph.includes(qLower) || aria.includes(qLower) || nm.includes(qLower)) score = 70;
                    
                    if (el.id) {{
                        try {{
                            const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                            if (l && (l.innerText.toLowerCase() === qLower || l.innerText.toLowerCase().includes(qLower))) score = Math.max(score, 95);
                        }} catch(e) {{}}
                    }}
                    const pLabel = el.closest('label');
                    if (pLabel && (pLabel.innerText.toLowerCase() === qLower || pLabel.innerText.toLowerCase().includes(qLower))) score = Math.max(score, 90);

                    if (score > bestScore) {{
                        bestScore = score;
                        best = el;
                    }}
                }}
                return best;
            }}

            for (const [key, value] of Object.entries(mapping)) {{
                const el = findField(key);
                if (!el) {{
                    errors.push({{ field: key, error: "Field not found" }});
                    continue;
                }}
                const tag = el.tagName.toLowerCase();
                const type = (el.type || '').toLowerCase();
                const role = (el.getAttribute('role') || '').toLowerCase();

                if (typeof value === 'boolean') {{
                    const isChecked = !!el.checked || el.getAttribute('aria-checked') === 'true';
                    if (isChecked !== value) {{
                        el.click();
                    }}
                }} else if (type === 'radio' || role === 'radio') {{
                    el.click();
                }} else if (tag === 'select' || role === 'combobox' || Array.isArray(value)) {{
                    const targetVal = String(Array.isArray(value) ? value[0] : value);
                    let foundOption = false;
                    if (el.options) {{
                        for (let i = 0; i < el.options.length; i++) {{
                            if (el.options[i].value === targetVal || el.options[i].text.trim() === targetVal) {{
                                el.selectedIndex = i;
                                foundOption = true;
                                break;
                            }}
                        }}
                    }}
                    if (!foundOption) el.value = targetVal;
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }} else {{
                    el.focus();
                    el.value = String(value);
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
                filledCount++;
            }}

            let submitted = false;
            if (submit) {{
                if (submit === true || String(submit).toLowerCase() === 'enter') {{
                    const form = document.querySelector('form');
                    if (form) {{
                        if (typeof form.requestSubmit === 'function') form.requestSubmit();
                        else form.submit();
                        submitted = true;
                    }}
                }} else {{
                    const submitStr = String(submit).toLowerCase();
                    const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"], a.btn');
                    for (const b of buttons) {{
                        if (!__cb_is_visible(b)) continue;
                        const txt = (b.innerText || b.value || b.getAttribute('aria-label') || '').trim().toLowerCase();
                        if (txt === submitStr || txt.includes(submitStr)) {{
                            b.click();
                            submitted = true;
                            break;
                        }}
                    }}
                }}
            }}

            return {{
                success: errors.length === 0,
                filled: filledCount,
                submitted: submitted,
                errors: errors
            }};
        }})()
        """

    @classmethod
    def decode_error(
        cls,
        err_data: Any,
        params: Optional[Dict[str, Any]] = None,
        auto_snapshot: Optional[str] = None,
    ) -> None:
        """Decode backend error JSON payload into domain exceptions with auto-snapshot recovery."""
        if isinstance(err_data, dict) and not auto_snapshot:
            auto_snapshot = err_data.get("auto_snapshot")

        target_loc = params.get("target") if params else None
        target_str = ""
        if isinstance(target_loc, dict):
            if target_loc.get("type") == "ref":
                target_str = f"[#{target_loc.get('refId')}]"
            else:
                target_str = str(target_loc.get("selector", ""))
        elif target_loc is not None:
            target_str = str(target_loc)

        tab_id = params.get("tabId") if params else None

        exc = None
        if isinstance(err_data, dict):
            code = err_data.get("code") or err_data.get("name")
            if code == "ELEMENT_NOT_FOUND" or "not found" in str(err_data.get("message", "")).lower():
                exc = ElementNotFoundError(
                    target=err_data.get("target", target_str),
                    tab_id=err_data.get("tabId", tab_id),
                    stale=err_data.get("stale", False),
                    suggestions=err_data.get("suggestions", []),
                    url=err_data.get("url", ""),
                )
            elif code == "ACTION_INTERCEPTED":
                exc = ActionInterceptionError(
                    target=err_data.get("target", target_str),
                    interceptor_tag=err_data.get("interceptorTag", "overlay"),
                    interceptor_ref=err_data.get("interceptorRef"),
                    interceptor_desc=err_data.get("interceptorDesc", ""),
                    tab_id=err_data.get("tabId", tab_id),
                )
            elif code == "TIMEOUT":
                exc = NavigationTimeoutError(
                    target=err_data.get("target", target_str),
                    timeout=err_data.get("timeout", 10.0),
                    url=err_data.get("url", ""),
                    ready_state=err_data.get("readyState", "unknown"),
                    dom_state=err_data.get("domState", "unknown"),
                    tab_id=err_data.get("tabId", tab_id),
                )
            else:
                exc = ChromeBridgeError(err_data.get("message", str(err_data)), tab_id=tab_id)
        else:
            err_str = str(err_data)
            if "not found" in err_str.lower():
                exc = ElementNotFoundError(target=target_str, tab_id=tab_id)
            elif "intercepted" in err_str.lower():
                exc = ActionInterceptionError(target=target_str, tab_id=tab_id)
            elif "timed out" in err_str.lower():
                exc = NavigationTimeoutError(target=target_str, tab_id=tab_id)
            else:
                exc = ChromeBridgeError(err_str, tab_id=tab_id)

        if auto_snapshot and exc:
            exc.auto_snapshot = auto_snapshot
        if exc:
            raise exc

    @classmethod
    def collect_fuzzy_suggestions(cls, tab: Any, query: str) -> List[Dict[str, Any]]:
        """Collect fuzzy interactive candidate matches from active DOM on element lookup failure."""
        try:
            js = f"""
            (() => {{
                const query = {json.dumps(query)}.toLowerCase();
                const all = document.querySelectorAll('button, a, input, select, textarea, [role]');
                const suggestions = [];
                for (const el of all) {{
                    const txt = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim();
                    if (!txt) continue;
                    const tLower = txt.toLowerCase();
                    if (tLower.includes(query) || query.includes(tLower) || tLower.slice(0, 3) === query.slice(0, 3)) {{
                        const role = el.getAttribute('role') || el.tagName.toLowerCase();
                        let ref = el.getAttribute('data-cbridge-id') || el.id || '';
                        suggestions.push({{
                            'ref': ref ? '#' + ref : '#element',
                            'role': role,
                            'name': txt.slice(0, 50)
                        }});
                        if (suggestions.length >= 5) break;
                    }}
                }}
                return suggestions;
            }})()
            """
            res = tab.eval_js(js)
            if isinstance(res, list):
                return res
            elif isinstance(res, dict) and isinstance(res.get("result"), list):
                return res["result"]
        except Exception:
            pass
        return []


# Backward-compatible alias
DomBatchSynthesizer = DomCompiler
