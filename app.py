from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from datetime import datetime

app = FastAPI(
    title="Learning Resources API",
    description="CRUD API for managing educational resources, tutorials, and documentation"
)

# Pydantic models
class ResourceBase(BaseModel):
    name: str
    description: str
    link: str
    category: Optional[str] = "General"
    tags: Optional[List[str]] = []

class ResourceCreate(ResourceBase):
    pass

class ResourceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None

class Resource(ResourceBase):
    id: int
    created_at: datetime
    updated_at: datetime

# In-memory database
resources_db = {}
resource_id_counter = 1

# Add some sample data
sample_resources = [
    {
        "name": "Video to Fork a Repo",
        "description": "This resource is for helping you to fork a repo from Github",
        "link": "https://youtube.com/wkeljrew",
        "category": "Git/GitHub",
        "tags": ["github", "git", "forking", "tutorial"]
    },
    {
        "name": "FastAPI Documentation",
        "description": "Official FastAPI documentation for building APIs",
        "link": "https://fastapi.tiangolo.com",
        "category": "Web Development",
        "tags": ["fastapi", "python", "api", "documentation"]
    }
]

# Initialize with sample data
for sample in sample_resources:
    now = datetime.now()
    resources_db[resource_id_counter] = {
        "id": resource_id_counter,
        **sample,
        "created_at": now,
        "updated_at": now
    }
    resource_id_counter += 1

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Learning Resources API!",
        "endpoints": {
            "docs": "/docs",
            "resources": "/resources",
            "categories": "/categories"
        }
    }

# CREATE - Add a new resource
@app.post("/resources/", response_model=Resource, status_code=201)
def create_resource(resource: ResourceCreate):
    global resource_id_counter
    
    now = datetime.now()
    new_resource = {
        "id": resource_id_counter,
        "name": resource.name,
        "description": resource.description,
        "link": resource.link,
        "category": resource.category,
        "tags": resource.tags,
        "created_at": now,
        "updated_at": now
    }
    
    resources_db[resource_id_counter] = new_resource
    resource_id_counter += 1
    
    return new_resource

# READ - Get all resources
@app.get("/resources/", response_model=List[Resource])
def read_resources(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    tag: Optional[str] = None
):
    resources = list(resources_db.values())
    
    # Filter by category if provided
    if category:
        resources = [r for r in resources if r["category"].lower() == category.lower()]
    
    # Filter by tag if provided
    if tag:
        resources = [r for r in resources if tag.lower() in [t.lower() for t in r["tags"]]]
    
    return resources[skip : skip + limit]

# READ - Get a single resource by ID
@app.get("/resources/{resource_id}", response_model=Resource)
def read_resource(resource_id: int):
    if resource_id not in resources_db:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resources_db[resource_id]

# UPDATE - Update a resource by ID
@app.put("/resources/{resource_id}", response_model=Resource)
def update_resource(resource_id: int, resource: ResourceUpdate):
    if resource_id not in resources_db:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    stored_resource = resources_db[resource_id]
    
    # Update only provided fields
    update_data = resource.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        stored_resource[key] = value
    
    stored_resource["updated_at"] = datetime.now()
    resources_db[resource_id] = stored_resource
    
    return stored_resource

# DELETE - Delete a resource by ID
@app.delete("/resources/{resource_id}")
def delete_resource(resource_id: int):
    if resource_id not in resources_db:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    deleted_resource = resources_db.pop(resource_id)
    return {
        "message": "Resource deleted successfully",
        "resource": deleted_resource
    }

# Search resources by name or description
@app.get("/resources/search/{query}", response_model=List[Resource])
def search_resources(query: str):
    query_lower = query.lower()
    results = [
        resource for resource in resources_db.values()
        if query_lower in resource["name"].lower() 
        or query_lower in resource["description"].lower()
    ]
    return results

# Get all unique categories
@app.get("/categories/")
def get_categories():
    categories = set(r["category"] for r in resources_db.values())
    return {"categories": sorted(list(categories))}

# Get all unique tags
@app.get("/tags/")
def get_tags():
    tags = set()
    for resource in resources_db.values():
        tags.update(resource["tags"])
    return {"tags": sorted(list(tags))}

# Get resources by category
@app.get("/categories/{category_name}", response_model=List[Resource])
def get_resources_by_category(category_name: str):
    results = [
        r for r in resources_db.values() 
        if r["category"].lower() == category_name.lower()
    ]
    if not results:
        raise HTTPException(
            status_code=404, 
            detail=f"No resources found in category: {category_name}"
        )
    return results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)