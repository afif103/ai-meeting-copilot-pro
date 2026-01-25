"""
Enhanced Anonymizer with Smart Privacy Protection
- Smart snippet extraction
- Multiple anonymization strategies
- PII detection and removal
- Configurable privacy levels
"""

import re
import hashlib


class Anonymizer:
    """Enhanced anonymization with multiple strategies"""

    # Privacy levels
    PRIVACY_LOW = "low"  # Only remove obvious numbers
    PRIVACY_MEDIUM = "medium"  # Remove numbers and common PII
    PRIVACY_HIGH = "high"  # Aggressive anonymization

    def __init__(self, privacy_level=PRIVACY_MEDIUM):
        self.privacy_level = privacy_level

        # PII patterns
        self.patterns = {
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
            "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            "url": r"https?://[^\s]+",
            "date": r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        }

    def anonymize(self, text, max_words=50):
        """
        Main anonymization method with smart snippet extraction
        """
        # Extract recent context (last N words)
        snippet = self._extract_snippet(text, max_words)

        # Apply privacy level
        if self.privacy_level == self.PRIVACY_HIGH:
            snippet = self._anonymize_high(snippet)
        elif self.privacy_level == self.PRIVACY_MEDIUM:
            snippet = self._anonymize_medium(snippet)
        else:
            snippet = self._anonymize_low(snippet)

        return snippet.strip()

    def _extract_snippet(self, text, max_words):
        """Extract the most recent and relevant part of text"""
        words = text.split()

        if len(words) <= max_words:
            return text

        # Take last N words for recency
        snippet = " ".join(words[-max_words:])

        # Ensure we start at a sentence boundary if possible
        sentences = snippet.split(". ")
        if len(sentences) > 1:
            # Skip incomplete first sentence
            snippet = ". ".join(sentences[1:])

        return snippet

    def _anonymize_low(self, text):
        """Low privacy: Only remove obvious numbers"""
        # Replace standalone numbers
        text = re.sub(r"\b\d+\b", "[NUMBER]", text)

        # Replace decimal numbers
        text = re.sub(r"\b\d+\.\d+\b", "[NUMBER]", text)

        return text

    def _anonymize_medium(self, text):
        """Medium privacy: Remove numbers and common PII"""
        # Start with low-level anonymization
        text = self._anonymize_low(text)

        # Remove emails
        text = re.sub(self.patterns["email"], "[EMAIL]", text)

        # Remove phone numbers
        text = re.sub(self.patterns["phone"], "[PHONE]", text)

        # Remove URLs
        text = re.sub(self.patterns["url"], "[URL]", text)

        # Remove dates
        text = re.sub(self.patterns["date"], "[DATE]", text)

        # Remove IP addresses
        text = re.sub(self.patterns["ip_address"], "[IP]", text)

        return text

    def _anonymize_high(self, text):
        """High privacy: Aggressive anonymization"""
        # Start with medium-level
        text = self._anonymize_medium(text)

        # Remove SSN
        text = re.sub(self.patterns["ssn"], "[SSN]", text)

        # Remove credit cards
        text = re.sub(self.patterns["credit_card"], "[CARD]", text)

        # Remove potential names (capitalized words, heuristic)
        # This is aggressive and may remove some legitimate words
        text = re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", "[NAME]", text)

        # Hash any remaining long numbers (potential IDs)
        def hash_long_numbers(match):
            num = match.group()
            if len(num) > 6:
                return f"[ID:{hashlib.md5(num.encode()).hexdigest()[:8]}]"
            return num

        text = re.sub(r"\d{7,}", hash_long_numbers, text)

        return text

    def detect_pii(self, text):
        """Detect potential PII in text"""
        findings = {}

        for pii_type, pattern in self.patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                findings[pii_type] = len(matches)

        return findings


# Convenience function for backward compatibility
def anonymize_transcript(transcript, max_words=50):
    """
    Extract a short, anonymized snippet from the transcript for API calls.
    - Takes the last N words to capture recent context
    - Removes numbers and PII to ensure privacy
    """
    anonymizer = Anonymizer(privacy_level=Anonymizer.PRIVACY_MEDIUM)
    return anonymizer.anonymize(transcript, max_words)


# Advanced function with configurable privacy
def anonymize_with_privacy(transcript, privacy_level="medium", max_words=50):
    """
    Anonymize with configurable privacy level

    Args:
        transcript: Text to anonymize
        privacy_level: "low", "medium", or "high"
        max_words: Maximum words in snippet

    Returns:
        Anonymized snippet
    """
    anonymizer = Anonymizer(privacy_level=privacy_level)
    return anonymizer.anonymize(transcript, max_words)


if __name__ == "__main__":
    print("[TEST] Testing Anonymizer...\n")

    # Test text with various PII
    test_text = """
    This is a long transcript with some numbers 123 and more text here.
    My email is john.doe@example.com and my phone is 555-123-4567.
    The meeting is scheduled for 12/25/2024 at our office.
    You can reach me at https://example.com or IP 192.168.1.1.
    My credit card is 4532-1234-5678-9010 and SSN is 123-45-6789.
    John Smith and Jane Doe will be attending.
    The transaction ID is 98765432109876543210.
    """

    # Test different privacy levels
    print("=" * 60)
    print("ORIGINAL TEXT:")
    print("=" * 60)
    print(test_text)
    print()

    print("=" * 60)
    print("LOW PRIVACY (numbers only):")
    print("=" * 60)
    result_low = anonymize_with_privacy(test_text, "low", max_words=100)
    print(result_low)
    print()

    print("=" * 60)
    print("MEDIUM PRIVACY (numbers + common PII):")
    print("=" * 60)
    result_medium = anonymize_with_privacy(test_text, "medium", max_words=100)
    print(result_medium)
    print()

    print("=" * 60)
    print("HIGH PRIVACY (aggressive):")
    print("=" * 60)
    result_high = anonymize_with_privacy(test_text, "high", max_words=100)
    print(result_high)
    print()

    # Test PII detection
    print("=" * 60)
    print("PII DETECTION:")
    print("=" * 60)
    anonymizer = Anonymizer()
    pii_found = anonymizer.detect_pii(test_text)
    for pii_type, count in pii_found.items():
        print(f"  {pii_type}: {count} found")
    print()

    # Test snippet extraction
    print("=" * 60)
    print("SNIPPET EXTRACTION (last 20 words):")
    print("=" * 60)
    snippet = anonymize_transcript(test_text, max_words=20)
    print(snippet)
    print()

    print("[OK] Test complete")
