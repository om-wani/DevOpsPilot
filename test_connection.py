import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url = os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key = os.getenv("AZURE_OPENAI_KEY"),
)

response = client.chat.completions.create(
    model = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
    messages = [{"role": "user", "content": "just say hello"}]
)

print(response.choices[0].message.content)