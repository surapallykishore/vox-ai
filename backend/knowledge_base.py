BUSINESS_INFO = {
    "name": "TechFlow Solutions",
    "type": "Technology Consulting",
    "hours": "Monday - Friday, 9:00 AM - 6:00 PM EST",
    "phone": "(555) 123-4567",
    "email": "support@techflow.example.com",
    "website": "techflow.example.com",
    "address": "123 Innovation Drive, Suite 400, San Francisco, CA 94105",
    "services": [
        "Web Development",
        "AI Integration",
        "Cloud Migration",
        "Mobile App Development",
        "DevOps Consulting",
    ],
    "pricing": {
        "starter": "$99/month - Basic web maintenance and support",
        "professional": "$499/month - Full-stack development and AI features",
        "enterprise": "$2,499/month - Dedicated team, 24/7 support, custom solutions",
    },
    "faq": {
        "refund_policy": (
            "We offer a 30-day money-back guarantee on all plans. "
            "No questions asked."
        ),
        "free_consultation": (
            "Yes! We offer a free 30-minute consultation to understand "
            "your needs and recommend the right plan."
        ),
        "contract_length": (
            "All plans are month-to-month with no long-term commitment required."
        ),
        "support_response_time": (
            "Starter: 24 hours. Professional: 4 hours. Enterprise: 1 hour."
        ),
        "technologies": (
            "We work with Python, JavaScript/TypeScript, React, Next.js, "
            "FastAPI, AWS, GCP, and all major AI/ML frameworks."
        ),
    },
}


def get_system_prompt() -> str:
    info = BUSINESS_INFO
    services = ", ".join(info["services"])
    pricing_lines = "\n".join(
        f"  - {name}: {desc}" for name, desc in info["pricing"].items()
    )
    faq_lines = "\n".join(
        f"  - {topic.replace('_', ' ').title()}: {answer}"
        for topic, answer in info["faq"].items()
    )

    return f"""You are a friendly, professional customer support agent for {info['name']}, \
a {info['type']} company.

Your job is to help callers with questions about our services, pricing, and policies. \
Be warm, concise, and helpful. Keep responses SHORT — ideally 1-3 sentences since this \
is a voice conversation and long responses sound unnatural.

IMPORTANT VOICE GUIDELINES:
- Speak naturally as if on a phone call
- Use short sentences
- Avoid bullet points, markdown, or formatting — this will be read aloud
- Don't say "I'd be happy to help" every time — vary your responses
- If you don't know something, offer to connect them with a human agent

BUSINESS INFORMATION:
- Company: {info['name']}
- Hours: {info['hours']}
- Phone: {info['phone']}
- Email: {info['email']}
- Services: {services}

PRICING:
{pricing_lines}

FREQUENTLY ASKED QUESTIONS:
{faq_lines}

Remember: you're on a live phone call. Be conversational, brief, and helpful."""
