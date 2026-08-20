import urllib.request, urllib.error
import json, os, re, base64

# Get API key
with open('config.js') as f:
    for line in f:
        m = re.search(r'GEMINI_API_KEY\s*=\s*[\"\']([^\"\']+)[\"\']', line)
        if m:
            api_key = m.group(1)
            break

# Load clean map
with open('public/clean_base_map.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

prompt = "Transform this map into a whimsical Italian trattoria style illustration. Make the roads look like long, winding strands of golden spaghetti pasta on a warm red-and-white checkered tablecloth background. Water bodies should be pools of rich olive oil with a golden-green shimmer. Vineyard and park areas should be clusters of bright basil leaves and tomatoes. Keep all geographic features and roads in exactly the same pixel positions, but give everything a playful, food-inspired Italian restaurant aesthetic. The overall feel should be warm, fun, inviting — like a placemat at a family-owned trattoria. Do not add any text labels. Use colors: tomato red (#E23D28), pasta gold (#F2C94C), basil green (#4A7C41), olive oil (#C7A94B), mozzarella white (#FFF5E1). Keep all roads, coastlines, water bodies, and markers in exactly the same pixel positions. Do not add any text labels."

payload = {
    "contents": [{
        "parts": [
            {
                "inlineData": {
                    "mimeType": "image/png",
                    "data": img_b64
                }
            },
            {
                "text": prompt
            }
        ]
    }],
    "generationConfig": {
        "responseModalities": ["IMAGE", "TEXT"],
        "temperature": 0.4
    }
}

print("Calling Nano Banana (Gemini 3.1 Flash Image Preview)...")
req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={api_key}",
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        res = json.loads(resp.read())
        
        # Extract image part
        try:
            parts = res['candidates'][0]['content']['parts']
            img_data = None
            for p in parts:
                if 'inlineData' in p and p['inlineData']['mimeType'].startswith('image/'):
                    img_data = p['inlineData']['data']
                    break
            
            if img_data:
                with open('/Users/joshyenne/.gemini/antigravity/brain/ef79e5ad-e85d-4f2d-bc07-f7b35b014e78/nano_spaghetti.png', 'wb') as f:
                    f.write(base64.b64decode(img_data))
                print("SUCCESS: Saved nano_spaghetti.png")
            else:
                print("ERROR: No image returned in response")
                print(json.dumps(res, indent=2))
        except Exception as e:
            print("ERROR parsing response:", e)
            print(json.dumps(res, indent=2))
except urllib.error.HTTPError as e:
    print(f"HTTP ERROR {e.code}: {e.read().decode('utf-8')}")
