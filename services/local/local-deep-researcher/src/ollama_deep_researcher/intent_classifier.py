"""
Intent Classifier for web research only.
Uses rule-based classification optimized for web search workflows.
"""

import re
import time
import logging
import requests
from typing import Dict, Any, Optional
from .configuration import Configuration

logger = logging.getLogger("ollama_deep_researcher.intent_classifier")

class IntentClassifier:
    """Rule-based intent classifier for web search only."""
    
    def __init__(self, config: Configuration):
        self.config = config
        
    def classify_intent(self, text: str) -> Dict[str, Any]:
        start_time = time.time()
        
        # Check if URL is present for direct content fetch
        url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
        has_url = bool(re.search(url_pattern, text))
        
        # Check for direct content request indicators (English and Thai)
        direct_indicators = [
            # English patterns
            r'\b(?:analyze|explain|summarize|review|examine|elaborate)\s+(?:this\s+)?(?:url|link|page|website|article)',
            r'\b(?:what|how)\s+(?:is|does|are)\s+(?:this|that)',
            r'\btell\s+me\s+about\s+(?:this|that)',
            r'\b(?:analyze|explain|summarize|elaborate|extract|interpret|decode|parse|process|digest|break down|break-down|breakdown|dissect|evaluate|assess|study|investigate|research|explore|examine|inspect|scrutinize|describe|detail|outline|overview|review|read|scan|understand|comprehend|grasp|decipher|translate|convert|transform|simplify|clarify|elucidate|expound|expand|discuss)\s+(?:https?://|www\.)',
            
            # Thai patterns
            r'(?:วิเคราะห์|อธิบาย|สรุป|ทบทวน|ตรวจสอบ)\s*(?:นี้\s*)?(?:url|ลิงก์|ลิงค์|หน้า|เว็บไซต์|เว็บ|บทความ)',
            r'(?:อะไร|ยังไง|เป็นยังไง|คืออะไร)\s*(?:คือ|เป็น)?\s*(?:นี่|นั่น|ของนี้)',
            r'(?:บอก|เล่า|อธิบาย|ขยายความ)(?:ให้|กับ)?(?:ฉัน|เรา|ผม)?\s*(?:เกี่ยวกับ|ถึง)?\s*(?:นี่|นั่น|ของนี้)',
            r'(?:วิเคราะห์|อธิบาย|สรุป|ขยายความ)\s*(?:https?://|www\.)',
            r'(?:ช่วย)?(?:วิเคราะห์|อธิบาย|สรุป|ทบทวน|ขยายความ)\s*(?:เนื้อหา|ข้อมูล)?\s*(?:ใน|จาก)?\s*(?:ลิงก์|ลิงค์|เว็บไซต์)',
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
    """Intent classifier with XLM-RoBERTa API for academic vs web classification."""
    
    def __init__(self, config: Configuration):
        self.simple_classifier = IntentClassifier(config)
        self.ml_api_url = "http://localhost:8762"
        
    def _classify_with_ml(self, text: str) -> Optional[Dict[str, Any]]:
        """Call XLM-RoBERTa API to determine search strategy."""
        try:
            response = requests.post(
                f"{self.ml_api_url}/classify",
                json={"text": text},
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                class_id = result.get("class_id")
                confidence = result.get("confidence", 0.8)
                
                # SearXNG already includes ArXiv results (hybrid)
                # Only use pure MCP for academic-only queries
                if class_id == 1:  # arxiv_only
                    intent = "ArXiv Research"
                    routing_strategy = "mcp"
                else:  # arxiv+web (2), web_only (3), out_of_domain (4)
                    intent = "Hybrid Research" if class_id == 2 else "Web Research"
                    routing_strategy = "web_search"  # SearXNG hybrid
                
                return {
                    "intent": intent,
                    "confidence": confidence,
                    "routing_strategy": routing_strategy,
                    "processing_time": result.get("processing_time", 0.0),
                    "classification_method": "xlm_roberta_api",
                    "confidence_level": "high" if confidence > 0.8 else "medium",
                    "ml_class_id": class_id,
                    "ml_class_label": result.get("class_label", "unknown")
                }
                    
        except requests.exceptions.RequestException:
            print("⚠️ ML API unavailable - using fallback")
        except Exception as e:
            print(f"⚠️ ML API error: {str(e)}")
            
        return None
        
    def classify_intent(self, text: str) -> Dict[str, Any]:
        """Classification: URLs → rule-based, unclear queries → ML model."""
        # Keep existing URL detection logic untouched
        rule_result = self.simple_classifier.classify_intent(text)
        
        # If URL detected or high confidence, use rule-based result
        if (rule_result.get("detection_signals", {}).get("has_url", False) or 
            rule_result.get("confidence", 0) > 0.9):
            return rule_result
            
        # For unclear queries, use ML model to determine academic vs web strategy
        ml_result = self._classify_with_ml(text)
        if ml_result and ml_result.get("confidence", 0) > 0.7:
            print(f"🤖 XLM-RoBERTa: {ml_result['intent']} → {ml_result['routing_strategy']}")
            return ml_result
            
        # Fallback to rule-based (web_search)
        return rule_result

# Factory function
def get_intent_classifier(config: Configuration) -> MLIntentClassifier:
    """Get intent classifier with ML API integration."""
    return MLIntentClassifier(config)

# Standalone function for easy use
def classify_query_intent(text: str, config: Configuration) -> Dict[str, Any]:
    """Classify query intent for web search."""
    classifier = get_intent_classifier(config)
    return classifier.classify_intent(text)

# Rule-based function
def intent_rule_based(research_topic: str) -> Dict[str, Any]:
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