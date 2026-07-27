import requests
import xml.etree.ElementTree as ET
from datetime import datetime

def test_ecfr_api():
    # We will test fetching Title 31 (Money and Finance), Part 1010 (General Provisions)
    # Using a recent fixed date to ensure the version exists
    test_date = "2026-07-01" 
    url = f"https://www.ecfr.gov/api/versioner/v1/full/{test_date}/title-31.xml?part=1010"
    
    print(f"Fetching from eCFR XML API: {url}")
    
    headers = {
        # Using a generic user agent, or specifying we are an API client
        "User-Agent": "ComplianceRAGBot/1.0 (contact@example.com)",
        "Accept": "application/xml"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            content_size = len(response.content)
            print(f"Success! Downloaded {content_size / 1024:.2f} KB of XML data.")
            
            # Print a snippet of the XML to verify it's the real regulatory text
            snippet = response.text[:500]
            print("\n--- XML Snippet ---")
            print(snippet)
            print("-------------------\n")
            
            # Try to quickly parse and count the number of <DIV8> (sections) to show scale
            try:
                root = ET.fromstring(response.content)
                sections = root.findall(".//DIV8")
                print(f"Found {len(sections)} sections (DIV8 elements) in Part 1010.")
            except Exception as e:
                print(f"Could not parse XML structure: {e}")
                
        else:
            print(f"Failed to fetch. Response text:\n{response.text[:500]}")
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_ecfr_api()
