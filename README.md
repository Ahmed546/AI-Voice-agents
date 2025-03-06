# AI-Voice-agents
An intelligent voice agent system that handles restaurant phone calls for order management, reservations, and customer inquiries.
# Restaurant AI Voice Agent

An intelligent voice agent system that handles restaurant phone calls for order management, reservations, and customer inquiries.

## Features

- **AI-Powered Conversations**: Natural language understanding and generation using state-of-the-art LLMs
- **Order Management**: Create, modify, and cancel orders through voice interactions
- **Reservation Handling**: Book and manage reservations
- **Context Awareness**: Maintains conversation context for natural interactions
- **Call Recording**: Records conversations for quality assurance and training
- **Analytics Dashboard**: Monitor system performance, sentiment analysis, and conversation metrics
- **Fallback to Humans**: Seamless transfer to staff when needed

## Architecture

The system uses a microservices architecture with the following components:

1. **FastAPI Backend**: Handles API requests, business logic, and database operations
2. **Twilio Integration**: Manages phone calls, speech recognition, and text-to-speech
3. **LLM Service**: Processes natural language using OpenAI or Anthropic models
4. **SQLite/PostgreSQL Database**: Stores conversation logs, orders, and system data
5. **Monitoring**: Prometheus metrics and logging

## Technology Stack

- **Python 3.8+**: Main programming language
- **FastAPI**: Web framework for API endpoints
- **SQLAlchemy**: ORM for database operations
- **Twilio**: Phone and SMS capabilities
- **OpenAI GPT**: Natural language processing
- **Pydantic**: Data validation and settings management
- **Prometheus**: Metrics and monitoring
- **Docker**: Containerization (optional)

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Twilio account with a phone number
- OpenAI API key
- PostgreSQL (for production) or SQLite (for development)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/restaurant-ai-voice-agent.git
   cd restaurant-ai-voice-agent
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

### Running the Application

1. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

2. Expose your local server for Twilio webhooks (in development):
   ```bash
   ngrok http 8000
   ```

3. Configure your Twilio phone number to use the ngrok URL as the webhook for incoming calls:
   ```
   Voice Webhook URL: https://your-ngrok-url.ngrok.io/api/voice/incoming
   ```

## Deployment

For production deployment, consider using Docker:

```bash
docker build -t restaurant-voice-agent .
docker run -p 8000:8000 restaurant-voice-agent
```

## Optimizations for Efficiency and Latency

The system implements several optimizations to minimize costs and latency:

1. **Two-Tier LLM Strategy**: Uses smaller, faster models for intent classification and larger models for complex responses
2. **Context Management**: Trims conversation history to fit token limits
3. **Asynchronous Processing**: Uses async/await for non-blocking operations
4. **Retry Mechanisms**: Implements exponential backoff for API calls
5. **Caching**: Caches frequently accessed data
6. **Database Indexing**: Optimized queries for faster data retrieval
7. **Error Handling**: Graceful degradation and fallbacks

## Security Considerations

- API keys and sensitive data are stored as environment variables
- Database connections use secure parameters
- Input validation using Pydantic
- CORS configuration for API endpoints
- Error logging without exposing sensitive information

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- OpenAI for GPT models
- Twilio for voice services
- FastAPI team for the excellent framework