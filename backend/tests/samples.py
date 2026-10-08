"""Synthetic resumes used across the tests. No real personal data."""

STRONG_AGENTIC = """\
Jane Doe
jane.doe@example.com | github.com/janedoe | +1 555 123 4567

SKILLS
Languages: Python, Java, JavaScript, SQL
Frameworks: FastAPI, LangChain, LangGraph, React, Next.js
Cloud & Tools: GCP, Docker, PostgreSQL, Redis

PROJECTS
Research Assistant Agent | Python, LangGraph, FastAPI
• Built a stateful agentic workflow with retrieval, tool calling, orchestration and an evaluation pipeline
• Implemented embeddings and vector search with document chunking over a Chroma vector store, with citations
• Async FastAPI backend with PostgreSQL and Redis caching, deployed on GCP Cloud Run using Docker

EXPERIENCE
Backend Intern, Acme Corp
• Developed Python microservices using FastAPI and wrote pytest unit tests
• Added structured logging and retry error handling

EDUCATION
B.Tech Computer Science
"""

RAG_PIPELINE = """\
Ravi Kumar
ravi@example.com

SKILLS
Python, FastAPI, Docker

PROJECTS
Document QA
• Built a RAG pipeline with document chunking, embeddings, vector retrieval and citations
"""

THIN_WRAPPER = """\
John Smith
john.smith@example.com

SKILLS
Python, Flask

PROJECTS
Chatbot
• We created a chatbot using OpenAI API
"""

JAVA_REACT_PYTHON_AI = """\
Priya Sharma
priya@example.com | https://github.com/priyasharma

SKILLS
Languages: Java, JavaScript, TypeScript, Python
Frontend: React, Next.js

PROJECTS
Document QA Assistant | Python, LangChain, React
• Built a RAG pipeline with embeddings and FAISS vector retrieval
• Next.js frontend and a Python API
"""

SKILLS_ONLY_FRAMEWORKS = """\
Sam Lee
sam@example.com

SKILLS
Languages: Python
AI: LangChain, LangGraph, LlamaIndex, RAG, Google ADK

PROJECTS
Inventory Tracker
• Built a CRUD app with Django and SQLite
"""

NO_PYTHON = """\
Alex Roe
alex@example.com

SKILLS
Java, Spring Boot, React, JavaScript

PROJECTS
Smart Search
• Built a RAG pipeline in Java with embeddings and vector search
"""

PYTHON_NO_AI = """\
Maria Gomez
maria@example.com

SKILLS
Python, Django, PostgreSQL

PROJECTS
Online Store
• Built an e-commerce backend in Python with Django and PostgreSQL

CERTIFICATIONS
Watched an AI tutorial about LLMs on YouTube
"""

PYTHON_ONLY_IN_TUTORIAL = """\
Tom Baker
tom@example.com

SUMMARY
I watched a Python tutorial last month.

SKILLS
Java, Spring

PROJECTS
Support Bot
• Built a RAG pipeline with embeddings and vector search in Java
"""

AI_ONLY_AS_BARE_KEYWORD = """\
Nina Park
nina@example.com

SKILLS
Python, SQL

SUMMARY
Passionate about AI and exploring LLMs.

PROJECTS
Weather App
• Built a weather dashboard using Python and Flask
"""
