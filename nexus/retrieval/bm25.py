"""Fast BM25 Okapi implementation for lexical search."""
import math
import re
from typing import List, Dict, Any, Tuple


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9_]+", text.lower())


class BM25Index:
    """In-memory BM25 Okapi index for lexical tool retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avg_doc_len = 0.0
        self.doc_ids: List[str] = []
        self.doc_lengths: List[int] = []
        self.doc_freqs: Dict[str, int] = {}
        self.term_freqs: List[Dict[str, int]] = []
        self.idf: Dict[str, float] = {}

    def index(self, documents: List[Tuple[str, str]]):
        """Index a list of (doc_id, text) tuples."""
        self.corpus_size = len(documents)
        self.doc_ids = []
        self.doc_lengths = []
        self.doc_freqs = {}
        self.term_freqs = []

        total_length = 0

        for doc_id, text in documents:
            self.doc_ids.append(doc_id)
            tokens = tokenize(text)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_length += doc_len

            # Calculate term frequencies for this doc
            tf: Dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self.term_freqs.append(tf)

            # Update document frequencies
            for token in tf.keys():
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        self.avg_doc_len = total_length / self.corpus_size if self.corpus_size > 0 else 0.0

        # Compute IDF for all vocabulary terms
        self.idf = {}
        for term, df in self.doc_freqs.items():
            # Standard Lucene/BM25 IDF formula with +1 to prevent negative weights
            self.idf[term] = math.log(1.0 + (self.corpus_size - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 15) -> List[Tuple[str, float]]:
        """Search query against index and return top_k (doc_id, score) pairs."""
        if self.corpus_size == 0:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores: List[float] = [0.0] * self.corpus_size

        for term in query_tokens:
            if term not in self.idf:
                continue
            term_idf = self.idf[term]

            for i in range(self.corpus_size):
                tf = self.term_freqs[i].get(term, 0)
                if tf == 0:
                    continue
                doc_len = self.doc_lengths[i]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                scores[i] += term_idf * (numerator / denominator)

        # Pair with doc_ids and sort descending
        ranked = [
            (self.doc_ids[i], scores[i])
            for i in range(self.corpus_size)
            if scores[i] > 0.0
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

