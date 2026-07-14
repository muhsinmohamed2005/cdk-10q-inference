from html.parser import HTMLParser
import re

BLOCK_TAGS = {"p", "div", "tr", "td", "br", "li", "h1", "h2", "h3", "table"}
# block tags unconditionally insert one space at their start and end.
# Whether that space ends up "necessary" or "redundant" depends entirely on
# whether the underlying text already had whitespace there -
# our code doesn't check that, it just always adds one,
# and we rely on a later normalization pass (collapsing multiple spaces
# into one) to clean up any resulting doubles.

SKIP_TAGS = {"style", "script"}
# these tags contain CSS/JS, not real content - we never want their
# text passed to handle_data at all, since it's meaningless noise
# (raw CSS rules, JS logic) not actual filing content.
# NOTE: this alone doesn't catch SEC's XBRL metadata block, which is
# wrapped in <div style="display:none"><ix:header>... rather than
# <style>/<script> - that's handled separately below via inline-style detection.


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []  # we'll collect chunks of text here as we parse
        self.skip_depth = 0   # >0 means we're currently inside a skip zone
        # (either <style>/<script>, OR any tag with inline style="display:none")
        self.hidden_stack = []
        # tracks, per opening tag, WHETHER that specific tag triggered a skip.
        # we need this (instead of just a counter) because handle_endtag only
        # gives us a tag NAME, not its original attributes - attributes only
        # exist on the opening tag. so we remember, tag-by-tag, whether THIS
        # one caused skip_depth to increment, so we know whether to decrement
        # it again when that same tag closes. without this, an unrelated
        # nested closing tag inside a hidden div could prematurely exit
        # skip-mode before we've actually left the hidden container.

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK_TAGS:
            self.text_parts.append(" ")  # insert a space so words don't run together

        is_skip_tag = tag in SKIP_TAGS
        attrs_dict = dict(attrs)
        style = attrs_dict.get("style", "").replace(" ", "")
        is_hidden_style = "display:none" in style
        # SEC wraps XBRL metadata like: <div style="display:none"><ix:header>...
        # catching the inline style directly is more reliable than trying to
        # name every possible XBRL tag (ix:header, ix:hidden, ix:nonFraction, etc.)

        if is_skip_tag or is_hidden_style:
            self.skip_depth += 1  # entering a skip zone
            self.hidden_stack.append(tag)
        else:
            self.hidden_stack.append(None)  # placeholder so stack depth matches nesting

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS:
            self.text_parts.append(" ")

        if self.hidden_stack:
            popped = self.hidden_stack.pop()
            if popped is not None:
                self.skip_depth -= 1  # leaving a skip zone (only if THIS tag caused it)

    def handle_data(self, data):
        # This method is called automatically every time the parser
        # encounters plain text (not a tag) while scanning the HTML.
        if self.skip_depth == 0:  # only collect text if we're NOT inside a skip zone
            self.text_parts.append(data)

    def handle_entityref(self, name):
        # called for named entities like &nbsp; &amp; &quot;
        if name == "nbsp":
            self.text_parts.append(" ")
        # (other named entities are rare in 10-Qs; ignore silently for now)

    def handle_charref(self, name):
        # called for numeric entities like &#160; (this is nbsp written numerically)
        if name in ("160", "xa0"):
            self.text_parts.append(" ")

def _normalize_whitespace(text):
    # collapses runs of spaces/tabs/newlines down to a single space,
    # and strips leading/trailing whitespace from the whole string.
    # this is where all those doubled-up spaces from BLOCK_TAGS insertion
    # (and the raw indentation from the HTML source itself) get cleaned up.
    text = re.sub(r'[ \t]+', ' ', text)      # collapse horizontal whitespace
    text = re.sub(r'\n\s*\n+', '\n\n', text)  # collapse multiple blank lines into one
    return text.strip()

def _truncate_to_budget(text, max_tokens):
    # rough heuristic: 1 token ≈ 4 characters (per course spec, not exact)
    max_chars = max_tokens * 4

    if len(text) <= max_chars:
        return text  # already fits, nothing to do

    # split into paragraphs (double-newline boundaries) and accumulate
    # until adding the next one would exceed budget - this avoids cutting
    # a sentence or number in half mid-way through.
    paragraphs = text.split('\n\n')
    result = []
    total_len = 0

    for para in paragraphs:
        if total_len + len(para) + 2 > max_chars:  # +2 accounts for the '\n\n' we'd rejoin with
            break
        result.append(para)
        total_len += len(para) + 2

    if result:
        return '\n\n'.join(result)

    # fallback: even the FIRST paragraph alone exceeds the budget -
    # split that one paragraph into sentences instead, and accumulate
    # sentence-by-sentence until we hit the budget.
    sentences = re.split(r'(?<=[.!?])\s+', paragraphs[0])
    result = []
    total_len = 0
    for sentence in sentences:
        if total_len + len(sentence) + 1 > max_chars:
            break
        result.append(sentence)
        total_len += len(sentence) + 1

    return ' '.join(result)

def extract_text(html: str, max_tokens: int) -> str:
    """
    Converts raw SEC 10-Q filing HTML into clean, prompt-ready plain text.
    Strips tags, CSS/JS, hidden XBRL metadata blocks, and normalizes
    whitespace. Truncates to approximately max_tokens, preserving whole
    paragraphs (or sentences, as a fallback) rather than cutting mid-word.
    """
    parser = TextExtractor()
    parser.feed(html)
    # .feed() is the method that starts the whole parsing process.
    # You hand it a string of HTML, and internally it scans through that
    # string character by character,
    # triggering handle_data/handle_starttag/handle_endtag automatically
    # as it recognizes each piece
    raw_extracted = "".join(parser.text_parts)
    normalized = _normalize_whitespace(raw_extracted)
    return _truncate_to_budget(normalized, max_tokens)

# --- test against a real 10-Q filing (AAPL 2026 Q2) ---
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/Users/muhsinmohamed05/sec-llm-service/document_retrieval")
    from sec_edgar_client import SecEdgar
    import requests

    se = SecEdgar('https://www.sec.gov/files/company_tickers.json')
    cik = se.ticker_to_cik("AAPL")[0]
    filing_url = se.quarterly_filing(cik, 2026, "Q2")

    headers = {"User-Agent": "Muhsin Mohamed muhsinmohamed2005@gmail.com"}
    raw_html = requests.get(filing_url, headers=headers).text

    result = extract_text(raw_html, max_tokens=5000)

    print("Raw HTML length:", len(raw_html))
    print("Extracted+truncated length:", len(result))
    print("Approx tokens:", len(result) // 4)
    print("---content---")
    print(result[:1500])



# Here's the main idea of what's going on:
# The parser is a scanner moving left to right through one giant string of HTML. It doesn't understand pages or documents — just characters, and it recognizes three basic shapes as it goes: opening tags (<div>), closing tags (</div>), and everything else (handle_data).
# It's carrying two things in its pocket as it walks: skip_depth (a number) and hidden_stack (a list). Think of skip_depth as a light switch counter — "how many layers deep am I inside something I should ignore right now." As long as it's 0, everything's fair game to collect. The moment it goes above 0, the parser goes quiet — it keeps walking and recognizing tags, but stops writing anything down.
# Early in the real Apple filing, the parser hits <div style="display:none">. It checks: does this tag's style attribute say display:none? Yes. So it flips the switch — skip_depth goes from 0 to 1. It also writes "div" onto the hidden_stack list, like a receipt saying "I turned the switch ON because of this specific div."
# Then it walks through everything inside that hidden div — <ix:header>, <ix:hidden>, all that XBRL gibberish text. Every time handle_data fires on that gibberish text, it checks skip_depth — sees it's 1, not 0 — and just... doesn't write it down. The words get "seen" but discarded, silently, one piece at a time.
# Eventually the parser reaches </div> — the closing match. It reaches into hidden_stack, pops the most recent receipt off the top ("div"), sees "oh, this receipt says I was the one who flipped the switch on" — so it flips it back off, skip_depth returns to 0.
# Why we need the receipt-list instead of just a plain counter: imagine somewhere inside that hidden div there's also an unrelated </span> closing tag that has nothing to do with hiding anything. Without the receipt system, we might accidentally decrement the switch for the wrong reason, turning "skip mode" off too early — while we're still technically inside the hidden div. The receipt makes sure only the exact tag that turned skip mode on is allowed to turn it back off.
# After the hidden div closes, the parser reaches the real content — UNITED STATES SECURITIES AND EXCHANGE COMMISSION — sees skip_depth is back to 0, and starts writing everything down again, word by word, all the way through the rest of the document.

# --- what happens after the parser finishes scanning the HTML ---
# parser.text_parts is a big list of small text chunks: real words, plus
# extra spaces we inserted at every block-tag boundary. "".join(...)
# glues it all into one messy (but complete) string.
# STATION 1 — _normalize_whitespace:
# tidies up the mess. Collapses repeated spaces into one, collapses
# multiple blank lines into a single paragraph break. Doesn't touch
# the actual content, just the spacing around it.
# STATION 2 — _truncate_to_budget:
# enforces the token budget (~4 characters per token, rough estimate).
# Tries to cut at a clean boundary, not mid-word/mid-number:
#   1. split into paragraphs, keep adding whole paragraphs until the
#      next one would exceed budget, then stop.
#   2. if even the FIRST paragraph alone is too big, fall back to
#      splitting that paragraph into sentences instead, and do the
#      same accumulate-until-budget trick at the sentence level.
# extract_text(html, max_tokens) — the "front door" function.
# Runs the whole sequence for you: feed the parser -> join the pieces
# -> normalize whitespace -> truncate to budget -> return one clean
# string.
#This is the only function Part 4 actually calls; everything else here just supports it internally.
