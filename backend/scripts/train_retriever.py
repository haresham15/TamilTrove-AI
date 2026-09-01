import hashlib
import json
import logging

import wandb
from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_triplets(file_path):
    with open(file_path, encoding='utf-8') as f:
        return json.load(f)

def prepare_training_data(triplets):
    train_examples = []
    for t in triplets:
        query = t["query"]
        pos_title = t["positive_movie"].get("title", "")
        pos_overview = t["positive_movie"].get("overview", "")
        neg_title = t["hard_negative_movie"].get("title", "")
        neg_overview = t["hard_negative_movie"].get("overview", "")
        
        pos_text = f"Title: {pos_title}. Overview: {pos_overview}"
        neg_text = f"Title: {neg_title}. Overview: {neg_overview}"
        
        # Format for MultipleNegativesRankingLoss: [Anchor, Positive, Negative]
        train_examples.append(InputExample(texts=[query, pos_text, neg_text]))
    return train_examples

def main():
    # Load the baseline model
    model_name = 'all-MiniLM-L6-v2'
    logger.info(f"Loading baseline model {model_name}...")
    model = SentenceTransformer(model_name)
    
    # Compute dataset version
    try:
        with open('data/movies_processed.json', 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()[:12]
            dataset_version = f"json-{digest}"
    except FileNotFoundError:
        dataset_version = "unknown-dataset"

    # Initialize wandb
    wandb.init(
        project="tamiltrove-retrieval",
        config={
            "dataset_version": dataset_version,
            "baseline_model": model_name,
            "epochs": 3,
            "batch_size": 16,
            "warmup_steps": 10
        }
    )
    
    # Load training triplets
    triplets_file = 'data/training_triplets.json'
    logger.info(f"Loading training triplets from {triplets_file}...")
    try:
        triplets = load_triplets(triplets_file)
    except FileNotFoundError:
        logger.error(f"Could not find {triplets_file}. Please run scripts/generate_triplets.py first.")
        return
        
    logger.info(f"Loaded {len(triplets)} triplets.")
    
    train_examples = prepare_training_data(triplets)
    
    # DataLoader
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
    
    # MultipleNegativesRankingLoss is standard for retrieval fine-tuning
    train_loss = losses.MultipleNegativesRankingLoss(model=model)
    
    logger.info("Starting fine-tuning...")
    
    # Train the model
    # We use a small number of epochs because the dataset is small and to avoid overfitting
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=3,
        warmup_steps=10,
        show_progress_bar=True
    )
    
    # Save the fine-tuned model
    output_path = f'models/finetuned-tamil-retriever-{dataset_version}'
    logger.info(f"Saving fine-tuned model to {output_path}...")
    model.save(output_path)
    logger.info("Fine-tuning complete!")
    wandb.finish()

if __name__ == '__main__':
    main()
