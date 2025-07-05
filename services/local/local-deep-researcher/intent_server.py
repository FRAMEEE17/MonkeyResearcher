import torch
import torch.nn as nn
import pickle
import time
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, XLMRobertaModel
from typing import Dict, Any, Optional
import uvicorn

class CustomXLMRobertaModel(nn.Module):
    def __init__(self, num_labels):
        super(CustomXLMRobertaModel, self).__init__()
        model_name = 'symanto/xlm-roberta-base-snli-mnli-anli-xnli'
        self.roberta = XLMRobertaModel.from_pretrained(model_name)
        self.dropout = nn.Dropout(0.2)
        self.classifier = nn.Sequential(
            nn.Linear(768, 512),
            nn.LayerNorm(512),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(512, num_labels)
        )
        self.loss = nn.CrossEntropyLoss()
        self.num_labels = num_labels

    def forward(self, input_ids, attention_mask, labels=None):
        output = self.roberta(input_ids=input_ids, attention_mask=attention_mask)
        output = self.dropout(output.pooler_output)
        logits = self.classifier(output)

        if labels is not None:
            loss = self.loss(logits.view(-1, self.num_labels), labels.view(-1))
            return {"loss": loss, "logits": logits}
        else:
            return {"logits": logits}

class IntentClassifierService:
    def __init__(self):
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.tokenizer = None
        self.label_encoder = None
        self.load_model()
        
    def load_model(self):
        """Load the XLM-RoBERTa intent classification model."""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Paths
            model_path = os.path.join(current_dir, "intent_classifier_xlm.pth")
            tokenizer_path = os.path.join(current_dir, "tokenizer_final")
            label_encoder_path = os.path.join(current_dir, "label_encoder_xlm.pkl")
            
            print(f"Loading model from: {model_path}")
            print(f"Loading tokenizer from: {tokenizer_path}")
            print(f"Loading label encoder from: {label_encoder_path}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
            
            # Load label encoder with encoding fix
            try:
                with open(label_encoder_path, 'rb') as f:
                    self.label_encoder = pickle.load(f, encoding='latin1')
            except:
                # Fallback: load with torch.load if pickle fails
                self.label_encoder = torch.load(label_encoder_path, map_location='cpu', weights_only=False)
            
            # Load model
            self.model = CustomXLMRobertaModel(num_labels=4)
            
            # Load state dict with error handling
            state_dict = torch.load(model_path, map_location='cpu', weights_only=True)
            
            # Remove problematic keys for transformer compatibility
            keys_to_remove = [k for k in state_dict.keys() if 'position_ids' in k]
            for key in keys_to_remove:
                del state_dict[key]
                
            self.model.load_state_dict(state_dict, strict=False)
            self.model.to(self.device)
            self.model.eval()
            
            print(f"✅ Intent classifier loaded successfully on {self.device}")
            print(f"📋 Available classes: {list(self.label_encoder.classes_)}")
            
        except Exception as e:
            print(f"❌ Failed to load intent classifier: {str(e)}")
            raise e
    
    def classify_intent(self, text: str) -> Dict[str, Any]:
        """Classify intent of input text."""
        if not self.model or not self.tokenizer or not self.label_encoder:
            raise HTTPException(status_code=500, detail="Model not loaded")
            
        try:
            start_time = time.time()
            
            # Tokenize input
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512
            ).to(self.device)
            
            # Predict
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs["logits"]
                probabilities = torch.softmax(logits, dim=-1)
                predicted_class_id = torch.argmax(probabilities, dim=-1).item()
                confidence = probabilities[0][predicted_class_id].item()
            
            # Get class label
            predicted_label = self.label_encoder.inverse_transform([predicted_class_id])[0]
            
            processing_time = time.time() - start_time
            
            return {
                "class_id": predicted_class_id + 1,  # Convert to 1-4 range
                "class_label": predicted_label,
                "confidence": round(confidence, 4),
                "processing_time": round(processing_time, 4),
                "probabilities": {
                    self.label_encoder.inverse_transform([i])[0]: round(probabilities[0][i].item(), 4)
                    for i in range(len(self.label_encoder.classes_))
                }
            }
            
        except Exception as e:
            print(f"❌ Classification failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")

# Initialize FastAPI app and classifier service
app = FastAPI(
    title="XLM-RoBERTa Intent Classifier",
    description="Fine-tuned XLM-RoBERTa model for research intent classification",
    version="1.0.0"
)

classifier_service = IntentClassifierService()

# Request/Response models
class ClassifyRequest(BaseModel):
    text: str
    
class ClassifyResponse(BaseModel):
    class_id: int
    class_label: str
    confidence: float
    processing_time: float
    probabilities: Dict[str, float]

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "device": str(classifier_service.device),
        "model_loaded": classifier_service.model is not None
    }

@app.post("/classify", response_model=ClassifyResponse)
def classify_text(request: ClassifyRequest) -> ClassifyResponse:
    """Classify intent of input text."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
        
    result = classifier_service.classify_intent(request.text)
    return ClassifyResponse(**result)

@app.get("/classes")
def get_classes():
    """Get available classification classes."""
    if classifier_service.label_encoder:
        return {
            "classes": list(classifier_service.label_encoder.classes_),
            "mapping": {
                "1": "arxiv_only",
                "2": "arxiv_web_hybrid", 
                "3": "web_only",
                "4": "out_of_domain"
            }
        }
    return {"error": "Label encoder not loaded"}

if __name__ == "__main__":
    print("🚀 Starting XLM-RoBERTa Intent Classification Server...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8762,
        reload=False,
        log_level="info"
    )