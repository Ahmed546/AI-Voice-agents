import os
import json
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

# Create OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

class VectorStore:
    """A simple vector store implementation for the restaurant knowledge base."""
    
    def __init__(self, knowledge_file: str = None):
        """Initialize the vector store with knowledge."""
        self.embedding_model = "text-embedding-ada-002"
        self.knowledge_base = []
        self.vector_store = []
        
        # Load knowledge from file if provided, otherwise use default
        if knowledge_file and os.path.exists(knowledge_file):
            self._load_knowledge_from_file(knowledge_file)
        else:
            self._load_default_knowledge()
            
        # Generate embeddings for all knowledge items
        self._generate_embeddings()
        
        logger.info(f"Vector store initialized with {len(self.knowledge_base)} knowledge items")
        
    def _load_knowledge_from_file(self, file_path: str):
        """Load knowledge base from a JSON file."""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                self.knowledge_base = data
                logger.info(f"Loaded knowledge base from {file_path}")
        except Exception as e:
            logger.error(f"Error loading knowledge base from {file_path}: {e}")
            self._load_default_knowledge()
            
    def _load_default_knowledge(self):
        """Load default knowledge base with restaurant information."""
        self.knowledge_base = [
            {
                "type": "restaurant_info",
                "content": f"Restaurant Name: {settings.RESTAURANT_NAME}\nHours: {settings.RESTAURANT_HOURS}\nDelivery available within {settings.DELIVERY_RADIUS} miles with a ${settings.DELIVERY_FEE} delivery fee.\nReservations required for parties of {settings.MIN_RESERVATION_SIZE} or more."
            },
            {
                "type": "menu_category",
                "category": "Appetizers",
                "content": "Our appetizers include: Garlic Bread ($5), Bruschetta ($7), Calamari ($12), Meatballs ($9), and Caprese Salad ($10)."
            },
            {
                "type": "menu_category",
                "category": "Pizzas",
                "content": "Our pizzas include: Margherita Pizza ($16, tomato sauce, fresh mozzarella, basil), Pepperoni Pizza ($18, tomato sauce, mozzarella, pepperoni), Vegetarian Pizza ($17, tomato sauce, mozzarella, bell peppers, mushrooms, onions), Supreme Pizza ($20, tomato sauce, mozzarella, pepperoni, sausage, bell peppers, onions, olives), and White Pizza ($19, olive oil, mozzarella, ricotta, garlic, spinach)."
            },
            {
                "type": "menu_category",
                "category": "Pasta",
                "content": "Our pasta dishes include: Spaghetti Bolognese ($15, beef and tomato sauce), Fettuccine Alfredo ($14, creamy parmesan sauce), Seafood Linguine ($22, shrimp, mussels, clams in white wine sauce), Lasagna ($16, layers of pasta, beef, and cheese), and Penne Arrabbiata ($13, spicy tomato sauce)."
            },
            {
                "type": "menu_category",
                "category": "Desserts",
                "content": "Our desserts include: Tiramisu ($8, coffee-flavored Italian dessert), Cannoli ($7, crispy pastry tubes filled with sweet ricotta), Gelato ($6, Italian ice cream in chocolate, vanilla, or pistachio), Panna Cotta ($7, Italian custard with berry sauce), and Chocolate Lava Cake ($9, warm chocolate cake with melted center)."
            },
            {
                "type": "menu_category",
                "category": "Drinks",
                "content": "Our drinks include: Soft Drinks ($3, Coke, Diet Coke, Sprite, Fanta), Italian Sodas ($4, flavored sodas with cream), Coffee ($3, espresso, americano, cappuccino, latte), Wine (house red or white, $7 per glass, $25 per bottle), and Beer ($5, domestic and imported options)."
            },
            {
                "type": "menu_item",
                "name": "Margherita Pizza",
                "category": "Pizzas",
                "price": 16.00,
                "description": "Our classic Margherita Pizza features a thin, crispy crust topped with San Marzano tomato sauce, fresh mozzarella cheese, fresh basil leaves, and a drizzle of extra virgin olive oil. It's then baked in our wood-fired oven for an authentic Italian taste.",
                "ingredients": ["San Marzano tomato sauce", "fresh mozzarella", "fresh basil", "extra virgin olive oil"],
                "dietary_info": "Vegetarian. Contains gluten and dairy."
            },
            {
                "type": "menu_item",
                "name": "Seafood Linguine",
                "category": "Pasta",
                "price": 22.00,
                "description": "Our Seafood Linguine features al dente linguine pasta tossed with fresh shrimp, mussels, and clams in a delicate white wine and garlic sauce with a touch of butter and fresh herbs.",
                "ingredients": ["linguine pasta", "shrimp", "mussels", "clams", "white wine", "garlic", "butter", "parsley"],
                "dietary_info": "Contains gluten, shellfish. Not suitable for shellfish allergies."
            },
            {
                "type": "menu_item",
                "name": "Tiramisu",
                "category": "Desserts",
                "price": 8.00,
                "description": "Our homemade Tiramisu is a classic Italian dessert made with layers of espresso-soaked ladyfingers and a light, creamy mascarpone filling, dusted with cocoa powder.",
                "ingredients": ["ladyfingers", "espresso", "mascarpone cheese", "eggs", "sugar", "cocoa powder"],
                "dietary_info": "Vegetarian. Contains gluten, dairy, and raw eggs."
            },
            {
                "type": "policy",
                "topic": "Delivery",
                "content": f"We offer delivery within {settings.DELIVERY_RADIUS} miles of our location. Delivery fee is ${settings.DELIVERY_FEE}. Minimum order for delivery is $20. Typical delivery time is 30-45 minutes but may be longer during peak hours. You can track your delivery through our website or app."
            },
            {
                "type": "policy",
                "topic": "Reservations",
                "content": f"Reservations are recommended for all guests and required for parties of {settings.MIN_RESERVATION_SIZE} or more. You can make reservations by phone or through our website. We hold reservations for 15 minutes past the scheduled time. For special events or large parties (10+), please contact our events coordinator."
            },
            {
                "type": "policy",
                "topic": "Special Dietary Needs",
                "content": "We offer gluten-free pasta and pizza crust options upon request for an additional $3. We can accommodate most common allergies and dietary restrictions with advance notice. Please inform your server of any allergies or dietary needs when ordering."
            },
            {
                "type": "special",
                "name": "Weekly Special",
                "content": "This week's special is our Chef's Special Truffle Mushroom Risotto ($24) - Creamy Arborio rice with wild mushrooms, truffle oil, and parmesan cheese. Available while supplies last."
            },
            {
                "type": "special",
                "name": "Happy Hour",
                "content": "Happy Hour is Tuesday through Friday from 4pm to 6pm. Enjoy $5 house wines, $4 draft beers, and half-price appetizers at the bar area only."
            }
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding for a text using OpenAI's API."""
        try:
            response = client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            # Return a vector of zeros as fallback
            return [0.0] * 1536  # Embedding size for text-embedding-ada-002
            
    def _generate_embeddings(self):
        """Generate embeddings for all knowledge items."""
        self.vector_store = []
        for item in self.knowledge_base:
            # Create a single string representation of the item
            if item['type'] == 'menu_item':
                text = f"{item['name']}: {item['description']} Price: ${item['price']:.2f}. Category: {item['category']}."
            else:
                text = item.get('content', '')
                
            # Generate embedding
            embedding = self._get_embedding(text)
            
            # Store item with its embedding
            self.vector_store.append({
                'item': item,
                'embedding': embedding,
                'text': text
            })
            
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
            
    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for relevant knowledge items given a query."""
        # Generate embedding for the query
        query_embedding = self._get_embedding(query)
        
        # Calculate similarity with all items
        results = []
        for item in self.vector_store:
            similarity = self._cosine_similarity(query_embedding, item['embedding'])
            results.append({
                'item': item['item'],
                'text': item['text'],
                'similarity': similarity
            })
            
        # Sort by similarity and return top_k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def search_by_type(self, query: str, item_type: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for relevant knowledge items of a specific type."""
        # Generate embedding for the query
        query_embedding = self._get_embedding(query)
        
        # Filter items by type and calculate similarity
        results = []
        for item in self.vector_store:
            if item['item']['type'] == item_type:
                similarity = self._cosine_similarity(query_embedding, item['embedding'])
                results.append({
                    'item': item['item'],
                    'text': item['text'],
                    'similarity': similarity
                })
                
        # Sort by similarity and return top_k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def get_menu_item(self, item_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific menu item by name."""
        for item in self.knowledge_base:
            if item['type'] == 'menu_item' and item['name'].lower() == item_name.lower():
                return item
        return None
    
    def get_menu_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all menu items in a category."""
        return [item for item in self.knowledge_base 
                if item['type'] == 'menu_item' and item['category'].lower() == category.lower()]
    
    def get_specials(self) -> List[Dict[str, Any]]:
        """Get all current specials."""
        return [item for item in self.knowledge_base if item['type'] == 'special']
    
    def get_policy(self, topic: str) -> Optional[Dict[str, Any]]:
        """Get a specific policy by topic."""
        for item in self.knowledge_base:
            if item['type'] == 'policy' and item['topic'].lower() == topic.lower():
                return item
        return None

# Create a singleton instance
vector_store = VectorStore()