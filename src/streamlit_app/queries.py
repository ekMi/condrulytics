TOP_RUNNERS = """
SELECT
    r.name_clean,
    COUNT(*) as races,
    AVG(f.speed_kmh) as avg_speed,
    MAX(f.speed_kmh) as best_speed
FROM fact_results f
JOIN dim_runner r ON f.runner_id = r.runner_id
GROUP BY r.name_clean
ORDER BY races DESC
LIMIT 20;
"""


TOP_RACES = """
SELECT
    ra.name,
    ra.year,
    ra.distance,
    COUNT(*) as participants,
    AVG(f.speed_kmh) as avg_speed
FROM fact_results f
JOIN dim_race ra ON f.race_id = ra.race_id
GROUP BY ra.name, ra.year, ra.distance
ORDER BY participants DESC
LIMIT 20;
"""
