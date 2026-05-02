import json
import boto3
from botocore.exceptions import ClientError

def initialize_bedrock():
    """Initialize the Bedrock client. Ensure AWS CLI is configured."""
    try:
        # If AWS CLI is configured (aws configure), this will pick up the credentials automatically
        client = boto3.client('bedrock-runtime', region_name='us-east-1') # Usually us-east-1 or us-west-2
        return client
    except Exception as e:
        print(f"  ❌ Failed to initialize AWS Bedrock client: {e}")
        return None

def generate_pitch(client, data: dict) -> dict:
    """
    Calls Bedrock (Claude 3 Haiku) to evaluate a lead and generate a pitch.
    Returns the original data dict with 'lead_score' and 'pitch' added.
    """
    if not client:
        data["lead_score"] = "N/A"
        data["pitch"] = "AWS Bedrock not configured."
        return data

    name = data.get("name", "Business")
    category = data.get("category", "Unknown Category")
    rating = data.get("rating", "")
    reviews = data.get("total_reviews", "")
    has_website = bool(data.get("website"))
    has_phone = bool(data.get("phone"))
    has_email = bool(data.get("email"))

    prompt = f"""
    You are an expert sales strategist. Analyze the following local business lead and do two things:
    1. Score the lead from 1 to 10 based on how urgently they need digital services (e.g., website building, SEO, digital marketing). 
       A business with NO website, high reviews, and a phone number is a HIGH score (8-10).
    2. Write a short, personalized 2-sentence pitch that I can send them via WhatsApp or email. Focus on the value of getting them online or improving their digital presence.

    Lead Details:
    - Name: {name}
    - Category: {category}
    - Rating: {rating}
    - Reviews: {reviews}
    - Has Website: {has_website}
    - Has Phone: {has_phone}
    - Has Email: {has_email}

    Output format:
    Provide your response in raw JSON format EXACTLY like this (do not wrap in markdown tags):
    {{
      "score": <number>,
      "pitch": "<2 sentence pitch>"
    }}
    """

    # We use Claude 3 Haiku because it's fast, cheap, and great at this task
    model_id = "anthropic.claude-3-haiku-20240307-v1:0"
    
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    })

    try:
        response = client.invoke_model(
            body=body,
            modelId=model_id,
            accept='application/json',
            contentType='application/json'
        )
        response_body = json.loads(response.get('body').read())
        content = response_body.get("content", [])[0].get("text", "{}")
        
        # Clean up in case Claude added markdown wrappers
        content = content.replace('```json', '').replace('```', '').strip()
        result = json.loads(content)
        
        data["lead_score"] = result.get("score", "N/A")
        data["pitch"] = result.get("pitch", "Error generating pitch")
        
    except Exception as e:
        print(f"  ⚠ Bedrock Error for {name}: {e}")
        data["lead_score"] = "Error"
        data["pitch"] = f"Failed: {str(e)}"

    return data

def enrich_records(records: list[dict]) -> list[dict]:
    """Process a batch of records through Bedrock."""
    client = initialize_bedrock()
    if not client:
        print("  ⚠ Skipping AI Enrichment because Bedrock client failed to initialize.")
        for r in records:
            r["lead_score"] = "N/A"
            r["pitch"] = "N/A"
        return records

    print(f"\n  🧠 Sending {len(records)} leads to AWS Bedrock for scoring and pitch generation...")
    enriched = []
    
    for i, record in enumerate(records):
        print(f"     Enriching [{i+1}/{len(records)}]: {record.get('name')} ... ", end="", flush=True)
        # We don't want to enrich records that we skipped entirely
        if not record.get("name"):
            enriched.append(record)
            continue
            
        updated_record = generate_pitch(client, record)
        enriched.append(updated_record)
        print(f"Score: {updated_record.get('lead_score')}")

    return enriched

if __name__ == "__main__":
    # Simple local test
    dummy_data = [{
        "name": "Raj Interior Designers",
        "category": "Interior Designer",
        "rating": "4.5",
        "total_reviews": "120",
        "website": "",
        "phone": "9876543210",
        "email": ""
    }]
    print("Testing Bedrock integration...")
    result = enrich_records(dummy_data)
    print(json.dumps(result, indent=2))
