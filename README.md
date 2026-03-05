# Monet Networks AI Probing Backend

This is the backend server for Monet Networks AI Probing, exposing interfaces to various AI-based models and services. It primarily provides a WebSocket proxy layer for the Probing Engine and dynamic database integration for survey and question metadata.

## Overview

The application is built using **FastAPI** and uses **Uvicorn** as the ASGI server. It acts as an intermediary, handling WebSocket connections from clients (like a frontend survey app), fetching relevant survey and question configurations from a database (MongoDB or MySQL), caching them in Redis, and proxying communication with a dedicated backend Probing Engine.

## Features

- **WebSocket Proxying (`/ws/probe_backend`)**: Matches a client's WebSocket connection and securely routes it to the `PROBE_ENGINE_WS_URL`. It validates survey details before starting/forwarding sessions.
- **Dynamic Database Switching (`DBSwitcher`)**: Supports fetching survey details dynamically from either **MongoDB** or **MySQL**, depending on the identifier types (`ObjectId` vs numeric IDs).
- **Redis Caching**: Caches survey and question configurations in Redis using the `survey_details:{su_id}:{qs_id}` key for fast retrieval during active WebSocket sessions.
- **State Management**: Maintains the current session state (e.g., current sequence/turn, session ID) in Redis while streaming interactions between the user and the Probe Engine.
- **Health Verification**: Exposes a standard `/health` REST endpoint to check server status.

## Directory Structure

*   **`main.py`**: The entry point for the FastAPI application. Sets up CORS, exception handling, and mounts the routers.
*   **`routes/websocket.py`**: Defines the `websocket_router`. Contains the WebSocket endpoint logic to manage client connectivity and broker messages to the downstream Probing Engine.
*   **`service/db_switcher.py`**: Business logic to decide which database (Mongo or MySQL) to query. Normalizes DB structures into standard memory schemas (Pydantic objects).
*   **`service/state_management.py`**: Helper functions for saving and loading probe session states from Redis.
*   **`models/`**: Contains Pydantic schemas representing Requests, Responses, Database objects, and Configuration schemas (e.g., `SurveyConfig`, `QuestionConfig`).
*   **`database/`**: Contains wrapper modules to set up connections to Mongo (`MongoWrapper.py`) and standard SQL connections (`SQL_Wrapper.py`).

## Requirements

Ensure you have the following installed. See `requirements.txt` for exact details.
- `fastapi`, `uvicorn`
- `redis`
- `pymongo`, `bson`
- `langchain_community` (for integrating memory/history if applicable)

## Environment Variables (.env)

The server relies on environment variables for configuration. Example configurations include:

```env
ENV=production # or development
REDIS_URL=redis://localhost:6379/0
REDIS_TTL_SECONDS_SURVEY=86400
PROBE_ENGINE_WS_URL=ws://localhost:8002/ws/probe_engine
```

## Running the Application

To run the application locally in development mode, you can use:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```