import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from pydantic import BaseModel, Field
from openai import OpenAI

# 1. Configuration & Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BACKEND_CRM_WEBHOOK = os.getenv("BACKEND_CRM_WEBHOOK", "https://api.yourbackend.com/v1/properties")

client = OpenAI(api_key=OPENAI_API_KEY)

# 2. Define Structured Data Schema using Pydantic
class PropertyListing(BaseModel):
    portal: str = Field(..., description="Source portal: Property Finder, Bayut, or Dubizzle")
    title: str = Field(..., description="Property title or headline")
    location: str = Field(..., description="Neighborhood or community in Dubai/Sharjah")
    price_aed: float = Field(..., description="Listing price in AED")
    property_type: str = Field(..., description="Apartment, Villa, Townhouse, etc.")
    bedrooms: int = Field(..., description="Number of bedrooms (0 for Studio)")
    amenities: list[str] = Field(default=[], description="List of key amenities mentioned")
    contact_phone: str = Field(..., description="Extracted agent or owner phone number if present")

# 3. LLM Extraction Logic
def extract_property_data(text_content: str) -> PropertyListing:
    prompt = f"""
    You are an expert real estate data parser for the UAE market. 
    Analyze the following text or message snippet from a property portal link/share 
    and extract all relevant details into the required schema.

    Content to analyze:
    {text_content}
    """

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "Extract structured real estate listing data accurately."},
                  {"role": "user", "content": prompt}],
        response_format=PropertyListing,
    )
    return completion.choices.message.parsed

# 4. Telegram Message Handler
async def handle_property_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text or update.message.caption
    if not message_text:
        return

    portals = ["propertyfinder.ae", "bayut.com", "dubizzle.com"]
    is_portal_link = any(portal in message_text.lower() for portal in portals)

    if not is_portal_link and len(message_text) < 30:
        return 

    await update.message.reply_text("🔍 Extracting property details and syncing with database...")

    try:
        extracted_data = extract_property_data(message_text)
        payload = extracted_data.model_dump()
        response = requests.post(BACKEND_CRM_WEBHOOK, json=payload, timeout=10)

        if response.status_code in [200, 201]:
            success_msg = (
                f"🧛‍♂️ **VampieePropertyBot: Synced Successfully!**\n\n"
                f"🏢 **Title:** {extracted_data.title}\n"
                f"📍 **Location:** {extracted_data.location}\n"
                f"💰 **Price:** AED {extracted_data.price_aed:,.0f}\n"
                f"🛏️ **Type:** {extracted_data.bedrooms} Bed {extracted_data.property_type}\n"
                f"📞 **Contact:** {extracted_data.contact_phone}"
            )
            await update.message.reply_text(success_msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Data extracted, but failed to sync with backend webhook.")

    except Exception as e:
        logger.error(f"Error processing listing: {e}")
        await update.message.reply_text("❌ Failed to parse or sync this property listing.")

# 5. Main Application Runner
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_property_message))
    logger.info("🤖 VampieePropertyBot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()