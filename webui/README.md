## Quick Start JAAA 

Follow these steps to set up and run the complete WebUI stack:

### 1. Start Search Engine (SearXNG)

First, start the SearXNG web search service:

```bash
cd searxng
bash start.sh
```

SearXNG provides privacy-respecting web search capabilities for the application.

### 2. Start Backend Pipeline

Next, start the local backend pipeline service:

```bash
cd local
bash start.sh
```

This runs the backend processing pipeline that handles data analysis and API requests.

### 3. Start Web Interface (Development Mode)

Finally, start the main web interface in development mode:

```bash
cd open-webui
npm install
npm run dev
```

The web interface will be available for development and testing.

## Components

- **`searxng/`** - Privacy-focused web search engine
- **`local/`** - Backend pipeline and data processing services  
- **`open-webui/`** - Main web user interface built with modern web technologies

## Prerequisites

- Node.js and npm (for open-webui)
- Bash shell environment
- Docker
