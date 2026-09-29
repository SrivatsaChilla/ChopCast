import sqlite3
import json

conn = sqlite3.connect('pireps.db')
cursor = conn.cursor()

# Get first 5 rows
cursor.execute("SELECT * FROM reports LIMIT 5")
rows = cursor.fetchall()

# Get column names
cols = [description[0] for description in cursor.description]

print(f"{' | '.join(cols)}")
print("-" * 100)
for row in rows:
    # The last column is raw_json, which is a string. We can format it slightly.
    formatted_row = [str(val) for val in row]
    print(" | ".join(formatted_row))

conn.close()
