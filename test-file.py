import csv
import random
 
OUTPUT_FILE = "msisdn_language.csv"
 
# Generate 100 unique 8-digit suffixes
numbers = random.sample(range(100_000_000), 100)
 
records = []
 
for i, number in enumerate(numbers):
    msisdn = f"+2517{number:08d}"  # 13 characters including +
    language = "en" if i < 50 else "am"
 
    records.append([msisdn, language])
 
# Randomize record order
random.shuffle(records)
 
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.writer(file)
    writer.writerow(["MSISDN", "LANGUAGE"])
    writer.writerows(records)
 
print(f"File created: {OUTPUT_FILE}")
print(f"Total records: {len(records)}")
print(f"English: {sum(r[1] == 'en' for r in records)}")
print(f"Amharic: {sum(r[1] == 'am' for r in records)}")
print(f"MSISDN length: {len(records[0][0])}")