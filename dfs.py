def dfs_search_v1(graph, start, target):
    """Find if target is reachable from start."""
    visited = set()
    stack = start  # Looks innocent enough...
   
    while stack:
        current = stack.pop()
       
        if current == target:
            return True
           
        if current not in visited:
            visited.add(current)
           
            for neighbor in graph[current]:
                if neighbor not in visited:
                    stack.append(neighbor)
   
    return False
