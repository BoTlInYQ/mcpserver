from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("News")

# Constants
NWS_API_BASE = "https://developer.nytimes.com/apis"
USER_AGENT = "News-app/1.0"