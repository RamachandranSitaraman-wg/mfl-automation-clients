import re
import requests
import tomli
from pathlib import Path


def get_phone_provider(phonenumber):
    """
    Standardizes a phone number to 10 digits and retrieves the carrier/provider information.

    Parameters:
    -----------
    phonenumber : str
        A US phone number in any format (e.g., "(727) 555-5555", "727-555-5555", "7275555555")

    Returns:
    --------
    str or None
        The carrier/provider name if successful, None if there's an error
    """

    # Step 1: Standardize phone number to 10 digits
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phonenumber)

    # Handle different formats
    if len(digits_only) == 11 and digits_only[0] == '1':
        # Remove leading '1' for US numbers
        standardized_phone = digits_only[1:]
    elif len(digits_only) == 10:
        standardized_phone = digits_only
    else:
        raise ValueError(f"Invalid phone number format. Expected 10 or 11 digits, got {len(digits_only)}")

    # Step 2: Load API token from secrets.toml
    secrets_path = Path(".streamlit/secrets.toml")

    try:
        with open(secrets_path, "rb") as f:
            secrets = tomli.load(f)
            api_token = secrets["rv_api_token"]
    except FileNotFoundError:
        raise FileNotFoundError("Could not find .streamlit/secrets.toml file")
    except KeyError:
        raise KeyError("'rv_api_token' not found in secrets.toml")

    # Step 3: Call the API
    api_url = "https://api.realvalidation.com/rpvWebService/TurboV3.php"
    params = {
        "output": "json",
        "phone": standardized_phone,
        "token": api_token
    }

    try:
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()

        # Step 4: Extract carrier information
        data = response.json()

        # Check if the call was successful
        if data.get("status") == "connected":
            carrier = data.get("carrier")
            return carrier
        else:
            error_text = data.get("error_text", "Unknown error")
            print(f"API returned status '{data.get('status')}': {error_text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error calling API: {e}")
        return None
    except ValueError as e:
        print(f"Error parsing JSON response: {e}")
        return None

if __name__ == "__main__":
    provider = get_phone_provider("510-320-7168") #AT&T

    print(provider)
# Example usage:
# provider = get_phone_provider("(727) 555-5555")
# print(f"Provider: {provider}")