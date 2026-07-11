import requests
import json
import string
import time

def fetch_all_trains():
    base_url = "https://www.railyatri.in/trains/sort_by_char/"
    all_trains = []
    
    # We will loop through a to z (and 0-9 just in case trains start with numbers)
    # string.ascii_lowercase gives 'abcdefghijklmnopqrstuvwxyz'
    # string.digits gives '0123456789'
    characters_to_search = string.ascii_lowercase + string.digits
    
    # Adding a standard User-Agent header helps prevent requests from being blocked
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    print("Starting data fetch...")

    for char in characters_to_search:
        url = f"{base_url}{char}"
        print(f"Fetching data for character: '{char.upper()}' -> {url}")
        
        try:
            response = requests.get(url, headers=headers)
            
            # Check if the request was successful
            if response.status_code == 200:
                try:
                    data = response.json()
                    trains = data.get("trains", [])
                    all_trains.extend(trains)
                    print(f"Found {len(trains)} trains for '{char}'.")
                except json.JSONDecodeError:
                    print(f"Failed to parse JSON for character '{char}'. The endpoint might be returning HTML.")
            else:
                print(f"Failed to fetch data for '{char}'. Status Code: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for '{char}': {e}")
        
        # Be polite to the server: wait 1 second before the next request
        time.sleep(1)

    # Build the final dictionary structure
    final_json_structure = {
        "total_trains_count": len(all_trains),
        "trains": all_trains
    }

    # Save all gathered data to a JSON file
    output_filename = "all_trains_data.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(final_json_structure, f, indent=4, ensure_ascii=False)
        
    print(f"\nSuccess! Total trains scraped: {len(all_trains)}")
    print(f"Data successfully saved to {output_filename}")

if __name__ == "__main__":
    fetch_all_trains()