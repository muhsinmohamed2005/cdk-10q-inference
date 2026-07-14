# -----VALIDATION LOGIC-----
import json

VALID_PERIODS = {"Q1", "Q2", "Q3", "Q4", "FY"}


def validate_request(event):
    # 'event' is the incoming request itself - a Python dict, already
    # parsed from JSON. Whatever the caller sent (e.g. the course's
    # example: {"question": "...", "ticker": "AMZN", "year": 2024, "period": "Q3"})
    # arrives here as this single dict. We don't build 'event' - it's
    # handed to us; our job is just to inspect it.
    """
    Checks the incoming request against the Lambda Contract.
    Returns None if valid, or a structured error dict if invalid.
    """
    required_fields = ["question", "ticker", "year", "period"]
    # this is just OUR OWN checklist - a plain list of strings naming
    # which keys the Lambda Contract says MUST exist in 'event'.
    # it has nothing to do with 'event' itself yet - it's a separate,
    # independent list we're about to compare against 'event'.

    for field in required_fields:
        if field not in event:
            return {"error": f"Missing required field: {field}"}

    ticker = event["ticker"]
    if not isinstance(ticker, str) or ticker != ticker.upper():
        return {"error": f"Ticker must be uppercase: got '{ticker}'"}

    period = event["period"]
    if period not in VALID_PERIODS:
        return {"error": f"Invalid period '{period}'. Must be one of {sorted(VALID_PERIODS)}"}

    year = event["year"]
    if not isinstance(year, int):
        return {"error": f"Year must be an integer: got {type(year).__name__}"}

    question = event["question"]
    if not isinstance(question, str) or not question.strip():
        return {"error": "Question must be a non-empty string"}

    return None  # all checks passed

#if __name__ == "__main__":
    # valid request
    #print(validate_request({"question": "What was revenue?", "ticker": "AAPL", "year": 2026, "period": "Q2"}))
    # missing field
    #print(validate_request({"question": "What was revenue?", "ticker": "AAPL", "year": 2026}))
    # lowercase ticker
    #print(validate_request({"question": "What was revenue?", "ticker": "aapl", "year": 2026, "period": "Q2"}))
    # bad period
    #print(validate_request({"question": "What was revenue?", "ticker": "AAPL", "year": 2026, "period": "Q5"}))


# -----10K/10Q DOCUMENT RETRIEVAL LOGIC-----
from sec_edgar_client import SecEdgar

def retrieve_filing(ticker, year, period):
    """
    Retrieves the raw filing HTML for the given ticker/year/period.
    FY maps to a 10-K (annual); Q1-Q4 map to a 10-Q (quarterly).
    Returns (filing_url, raw_html) or (None, None) if not found.
    """
    se = SecEdgar('https://www.sec.gov/files/company_tickers.json')
    cik_result = se.ticker_to_cik(ticker)

    if cik_result is None:
        return None, None  # ticker not found in SEC's database at all

    cik = cik_result[0]

    if period == "FY":
        filing_url = se.annual_filing(cik, year)
    else:
        filing_url = se.quarterly_filing(cik, year, period)

    if filing_url is None:
        return None, None  # no matching filing found for this year/period

    import requests
    headers = {"User-Agent": "Muhsin Mohamed muhsinmohamed2005@gmail.com"}
    resp = requests.get(filing_url, headers=headers)
    raw_html = resp.text

    return filing_url, raw_html

#if __name__ == "__main__":
    #filing_url, raw_html = retrieve_filing("AAPL", 2026, "Q2")
    #print(filing_url)
    #print(len(raw_html) if raw_html else None)

# -----10K/10Q DOCUMENT RAW HTML EXTRACTION LOGIC-----
from extract_text import extract_text

CONTEXT_WINDOW = 200_000  # Claude Sonnet 4.5 on Bedrock - confirmed via AWS model card
TOKEN_BUDGET = int(CONTEXT_WINDOW * 0.8)  # reserve 80% for filing text, per spec


def extract_filing_text(raw_html, max_tokens=TOKEN_BUDGET):
    return extract_text(raw_html, max_tokens)

#if __name__ == "__main__":
    #url, html = retrieve_filing("AAPL", 2026, "Q2")
    #extracted = extract_filing_text(html)
    #print(len(extracted))
    #print(extracted[:500])

# -----BEDROCK MODEL PROMPT BUILDING + INVOKE-----
import boto3
import time
import os

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

client = boto3.client("bedrock-runtime", region_name="us-east-1")


def build_prompt(question, ticker, period, year, extracted_text):
    return f"""Using only the SEC filing text provided below, answer the following question. If the answer is not contained in the filing, say so explicitly.

Question: {question}

Filing ({ticker} {period} {year}):
{extracted_text}"""


def invoke_model(prompt):
    start = time.perf_counter()

    response = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}]
    )

    latency_ms = int((time.perf_counter() - start) * 1000)

    answer = response["output"]["message"]["content"][0]["text"]
    usage = response["usage"]

    return {
        "answer": answer,
        "meta": {
            "model": MODEL_ID,
            "input_tokens": usage["inputTokens"],
            "output_tokens": usage["outputTokens"],
            "latency_ms": latency_ms
        }
    }

#if __name__ == "__main__":
    #url, html = retrieve_filing("MSFT", 2026, "Q3")
    #extracted_text = extract_filing_text(html)
    #prompt = build_prompt("What was Microsoft's total net sales for fiscal Q3 2026?", "MSFT", "Q3", 2026, extracted_text)
    #result = invoke_model(prompt)
    #print(result)


# -----THE ORCHESTRATING 'HANDLER' FUNCTION FOR AWS LAMBDA-----
def handler(event, context):
    """
    The actual Lambda entry point. AWS calls this function directly.
    'event' is the incoming request dict; 'context' is AWS runtime metadata
    (we don't use it here, but Lambda always passes it).
    """
    # Step 1: Validate
    validation_error = validate_request(event)
    if validation_error is not None:
        return {
            "statusCode": 400,
            "body": json.dumps(validation_error)
            # json is Python's standard library module for converting between Python objects
            # and JSON text (imported via import json, which is already at the top of your file).
            # .dumps stands for "dump string" — it takes a Python object (a dict, list, etc.)
            # and converts it into a plain text string formatted as valid JSON.
        }

    question = event["question"]
    ticker = event["ticker"]
    year = event["year"]
    period = event["period"]

    # Step 2: Retrieve
    try:
        filing_url, raw_html = retrieve_filing(ticker, year, period)
    except Exception as e:
        return {
            "statusCode": 502,
            "body": json.dumps({"error": f"Failed to retrieve filing from SEC EDGAR: {str(e)}"})
        }

    if raw_html is None:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": f"No {period} filing found for {ticker} in {year}"})
        }

    # Step 3: Extract
    try:
        extracted_text = extract_filing_text(raw_html)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed to extract filing text: {str(e)}"})
        }

    # Step 4: Invoke
    try:
        prompt = build_prompt(question, ticker, period, year, extracted_text)
        result = invoke_model(prompt)
    except Exception as e:
        return {
            "statusCode": 502,
            "body": json.dumps({"error": f"Bedrock invocation failed: {str(e)}"})
        }

    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }

if __name__ == "__main__":
    test_event = {
        "question": "What was Apple's total net sales for fiscal Q2 2026?",
        "ticker": "AAPL",
        "year": 2026,
        "period": "Q2"
    }
    print(handler(test_event, None))
