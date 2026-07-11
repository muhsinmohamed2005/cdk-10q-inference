import boto3
import os

client = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

response = client.converse(
    modelId="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    messages=[
        {
            "role": "user",
            "content": [
                {"text": "What was Apple's total net sales for fiscal Q2 2026?"}
            ]
        }
    ]
)

print(response["output"]["message"]["content"][0]["text"])
