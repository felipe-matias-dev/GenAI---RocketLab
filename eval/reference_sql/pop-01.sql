SELECT m.titulo AS key_titulo, f.popularidade AS metric_popularidade
FROM dim_movies m JOIN fact_movies_performance f USING (sk_movie_id)
WHERE f.popularidade IS NOT NULL
ORDER BY f.popularidade DESC, m.titulo LIMIT 8
