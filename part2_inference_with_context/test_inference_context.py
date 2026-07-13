
# Step 1: retrieve the EDGAR filing URL (Apple 2026 Q2) from sec_edgar_cient.py

import sys
sys.path.insert(0, "/Users/muhsinmohamed05/sec-llm-service/document_retrieval")
from sec_edgar_client import SecEdgar
import requests
import re

se = SecEdgar('https://www.sec.gov/files/company_tickers.json')
result = se.ticker_to_cik("AAPL")
cik = result[0]

filing_url = se.quarterly_filing(cik, 2026, "Q2")
# print(filing_url)

# Step 2: Download the actual filing HTML
headers = {"User-Agent": "Muhsin Mohamed muhsinmohamed2005@gmail.com"}
resp = requests.get(filing_url, headers=headers)
raw_html = resp.text

# Step 3: strip HTML tags down to plain, readable text
filing_text = re.sub(r'<[^>]+>', ' ', raw_html)
filing_text = re.sub(r'\s+', ' ', filing_text).strip()
# print(len(filing_text))  # sanity check to see how many characters we're working with
# print(filing_text[:500])
# print("111,184" in filing_text) # verifying that the AAPL Q2 2026 file generated correctly.

# Step 4: Locate the relevant section for our question (total net sales) and truncate around it.
idx = filing_text.find("Total net sales")
context_window = filing_text[max(0, idx-1000) : idx+4000]
# print(context_window)

# Step 5: Build the Bedrock prompt:
question = "What was Apple's total net sales for fiscal Q2 2026?"

prompt = f"""Using the information below, answer the following question.

Question: {question}

Document:
{context_window}"""

# print(prompt[:300])  # quick sanity check that it assembled correctly

# Step 6: The Bedrock LLM (Claude Sonnet 4.5) Call:
import boto3
import os

client = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")  # from reference/models.md

response = client.converse(
    modelId=MODEL_ID,
    messages=[{"role": "user", "content": [{"text": prompt}]}]
)

print(response["output"]["message"]["content"][0]["text"])
