
import os
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

print("Sending request to Gemini...")

start = time.time()

try:
    response = client.interactions.create(
        model="gemini-3.8-flash",
        input="Reply with only the word SUCCESS."
    )

    print("Gemini response:", response.output_text)

except Exception as e:
    print("Error:", e)

print("Time taken:", round(time.time() - start, 2), "seconds")
