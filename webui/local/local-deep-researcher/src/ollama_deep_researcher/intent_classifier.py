"""
Simplified Intent Classifier for web research only.
Uses rule-based classification optimized for web search workflows.
"""

import re
import time
import logging
from typing import Dict, Any, Optional
from .configuration import Configuration

logger = logging.getLogger("ollama_deep_researcher.intent_classifier")

class SimpleIntentClassifier:
    """Simplified rule-based intent classifier for web search only."""
    
    def __init__(self, config: Configuration):
        self.config = config
        
    def classify_intent(self, text: str) -> Dict[str, Any]:
        """Classify research intent - always returns web_search for simplified pipeline."""
        start_time = time.time()
        
        # Check if URL is present for direct content fetch
        url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
        has_url = bool(re.search(url_pattern, text))
        
        # Check for direct content request indicators
        direct_indicators = [
            r'\b(?:analyze|explain|summarize|review|examine)\s+(?:this\s+)?(?:url|link|page|website|article)',
            r'\b(?:what|how)\s+(?:is|does|are)\s+(?:this|that)',
            r'\btell\s+me\s+about\s+(?:this|that)',
            r'\b(?:analyze|explain|summarize)\s+(?:https?://|www\.)',
        ]
        
        is_direct_request = any(re.search(pattern, text, re.IGNORECASE) for pattern in direct_indicators)
        
        # Determine strategy
        if has_url and is_direct_request:
            intent = "url_fetch"
            routing_strategy = "url_fetch"
            confidence = 0.95
        else:
            intent = "web_search"
            routing_strategy = "web_search"
            confidence = 0.90
        
        processing_time = time.time() - start_time
        
        return {
            "intent": intent,
            "confidence": confidence,
            "routing_strategy": routing_strategy,
            "processing_time": processing_time,
            "classification_method": "simplified_rule_based",
            "confidence_level": "high" if confidence > 0.85 else "medium",
            "detection_signals": {
                "has_url": has_url,
                "is_direct_request": is_direct_request
            },
            "optimized_for": "web_search_only"
        }

class MLIntentClassifier:
    """Placeholder for ML-based intent classifier - fallback to simple classifier."""
    
    def __init__(self, config: Configuration):
        self.simple_classifier = SimpleIntentClassifier(config)
        
    def classify_intent(self, text: str) -> Dict[str, Any]:
        """Fallback to simple classification."""
        return self.simple_classifier.classify_intent(text)

# Factory function
def get_intent_classifier(config: Configuration) -> SimpleIntentClassifier:
    """Get intent classifier instance for web search only."""
    return SimpleIntentClassifier(config)

# Standalone function for easy use
def classify_query_intent(text: str, config: Configuration) -> Dict[str, Any]:
    """Classify query intent for web search."""
    classifier = get_intent_classifier(config)
    return classifier.classify_intent(text)

# Simple rule-based function
def intent_rule_based(research_topic: str) -> Dict[str, Any]:
    """Quick rule-based intent classification - always web search."""
    # Check for URL
    url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
    has_url = bool(re.search(url_pattern, research_topic))
    
    if has_url:
        return {
            "intent": "url_fetch",
            "confidence": 0.95,
            "routing_strategy": "url_fetch"
        }
    else:
        return {
            "intent": "web_search", 
            "confidence": 0.90,
            "routing_strategy": "web_search"
        }