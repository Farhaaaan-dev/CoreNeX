
import pandas as pd
import ast
from collections import Counter

FILE = "data_jobs.csv"
CHUNK_SIZE = 50000

print("CORENEX: Building weekly skill demand dataset...")

weekly_counts = Counter()
total_jobs = 0
valid_jobs = 0

def extract_skills(value):
    if not isinstance(value, str):
        return []

    try:
        parsed = ast.literal_eval(value)

        if isinstance(parsed, list):
            return [
                str(skill).strip().lower()
                for skill in parsed
                if skill
            ]

        return []
    except (ValueError, SyntaxError):
        return []

for chunk in pd.read_csv(
    FILE,
    usecols=["job_posted_date", "job_skills"],
    chunksize=CHUNK_SIZE
):

    total_jobs += len(chunk)

    chunk["date"] = pd.to_datetime(
        chunk["job_posted_date"],
        errors="coerce"
    )

    chunk = chunk.dropna(subset=["date"])

    chunk["week"] = (
        chunk["date"]
        .dt.to_period("W")
        .dt.start_time
    )

    chunk["skills"] = chunk["job_skills"].apply(
        extract_skills
    )

    chunk = chunk.explode("skills")
    chunk = chunk.dropna(subset=["skills"])

    chunk = chunk[chunk["skills"] != ""]

    valid_jobs += len(chunk)

    counts = chunk.groupby(
        ["week", "skills"]
    ).size()

    for (week, skill), count in counts.items():
        weekly_counts[(week, skill)] += int(count)

    print("Processed:", total_jobs, "job records")

print("\nCreating final dataset...")

result = pd.DataFrame(
    [
        {
            "week": week,
            "skill": skill,
            "demand": count
        }
        for (week, skill), count in weekly_counts.items()
    ]
)

result = result.sort_values(["week", "skill"])

result.to_csv(
    "weekly_skill_demand.csv",
    index=False
)

print("\nSUCCESS!")
print("Total jobs processed:", total_jobs)
print("Skill records extracted:", valid_jobs)
print("Unique skills:", result["skill"].nunique())
print("Weekly records:", len(result))
print("\nTop 15 skills:")

print(
    result.groupby("skill")["demand"]
    .sum()
    .sort_values(ascending=False)
    .head(15)
)

print("\nSaved: weekly_skill_demand.csv")
