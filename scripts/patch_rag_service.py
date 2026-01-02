import sys

file_path = "app/application/services/rag_service.py"
target_line = "                retrieval_result = await self._retrieve_context(user_id, query, top_k)"
replacement_block = """                # Expand query if needed
                expanded_query = await self._expand_query(query)
                retrieval_result = await self._retrieve_context(user_id, expanded_query, top_k)"""

with open(file_path, "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.rstrip() == target_line.rstrip():
        new_lines.append(replacement_block + "\n")
    else:
        new_lines.append(line)

with open(file_path, "w") as f:
    f.writelines(new_lines)

print("Patched successfully.")
