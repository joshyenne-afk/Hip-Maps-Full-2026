import urllib.request, json, re, base64

with open('config.js') as f:
    api_key = re.search(r'GEMINI_API_KEY\s*=\s*[\"\']([^\"\']+)[\"\']', f.read()).group(1)

with open('public/clean_base_map.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

prompt = "Transform this map into an elegant Italian illustration. Make the roads look like long, winding strands of golden spaghetti pasta. The background should be a warm, clean parchment texture. Water bodies should be pools of rich olive oil. Keep all geographic features and roads in exactly the same pixel positions. Do not add any text labels, plants, or distracting background patterns (NO plaid, NO checkered tablecloths). Keep the background clean and simple. Use colors: parchment beige (#F5E6C8), pasta gold (#F2C94C), olive oil (#C7A94B). Keep all roads, coastlines, water bodies, and markers in exactly the same pixel positions."

payload = {
    "contents": [{"parts": [{"inlineData": {"mimeType": "image/png", "data": img_b64}}, {"text": prompt}]}],
    "generationConfig": {"responseModalities": ["IMAGE"], "temperature": 0.4}
}

req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent?key={api_key}",
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        res = json.loads(resp.read())
        for p in res['candidates'][0]['content']['parts']:
            if 'inlineData' in p and p['inlineData']['mimeType'].startswith('image/'):
                with open('poc_base_map.png', 'wb') as f:
                    f.write(base64.b64decode(p['inlineData']['data']))
                print("SUCCESS: Saved poc_base_map.png")
                break
except Exception as e:
    print(e)
