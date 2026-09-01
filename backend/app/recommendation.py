from __future__ import annotations

import logging
from typing import Any

import scipy.sparse as sp

logger = logging.getLogger("tamiltrove.recommender")

class ALSRecommender:
    def __init__(self, catalog: Any, store: Any):
        self.catalog = catalog
        self.store = store
        self.model = None
        self.user_item_matrix = None
        self.user_id_map: dict[str, int] = {}
        self.item_id_map: dict[str, int] = {}
        self.item_id_reverse_map: dict[int, str] = {}
        
        for idx, movie in enumerate(self.catalog.movies):
            self.item_id_map[movie.id] = idx
            self.item_id_reverse_map[idx] = movie.id
            
        try:
            from implicit.als import AlternatingLeastSquares
            self.model_class = AlternatingLeastSquares
        except ImportError:
            logger.warning("implicit library not found, ALS Recommender disabled.")
            self.model_class = None

    def fit(self) -> None:
        """Fetch all interactions and train the ALS model."""
        if self.model_class is None:
            return

        interactions = self.store.list_all_interactions()
        
        user_indices = []
        item_indices = []
        weights = []

        user_count = 0
        for interaction in interactions:
            user_id = interaction["user_id"]
            movie_id = interaction["movie_id"]
            
            if movie_id not in self.item_id_map:
                continue
                
            if user_id not in self.user_id_map:
                self.user_id_map[user_id] = user_count
                user_count += 1
                
            user_idx = self.user_id_map[user_id]
            item_idx = self.item_id_map[movie_id]
            
            # Map interaction types to implicit weights
            weight = 1.0
            itype = interaction["interaction_type"]
            if itype == "like":
                weight = 5.0
            elif itype == "rating":
                weight = float(interaction.get("value") or 3.0)
            elif itype == "save":
                weight = 3.0
            elif itype == "dislike":
                weight = -5.0
            elif itype == "dismiss":
                weight = -2.0
            
            if weight > 0:
                user_indices.append(user_idx)
                item_indices.append(item_idx)
                weights.append(weight)

        if not user_indices:
            return
            
        # Create sparse matrix: users x items
        self.user_item_matrix = sp.csr_matrix(
            (weights, (user_indices, item_indices)),
            shape=(len(self.user_id_map), len(self.item_id_map))
        )
        
        self.model = self.model_class(factors=64, regularization=0.1, iterations=15)
        self.model.fit(self.user_item_matrix, show_progress=False)
        
    def recommend(self, user_id: str, k: int = 20) -> list[str]:
        """Return top k movie IDs for a user based on ALS."""
        if not self.model or user_id not in self.user_id_map:
            return []
            
        user_idx = self.user_id_map[user_id]
        
        try:
            ids, _ = self.model.recommend(
                user_idx, 
                self.user_item_matrix[user_idx], 
                N=k,
                filter_already_liked_items=True
            )
            return [self.item_id_reverse_map[i] for i in ids]
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return []
