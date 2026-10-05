SELECT m.titulo AS key_titulo, ABS(f.nota_tmdb - f.nota_imdb) AS metric_divergencia
FROM dim_movies m JOIN fact_movies_performance f USING (sk_movie_id)
WHERE f.nota_tmdb IS NOT NULL AND f.nota_imdb IS NOT NULL
ORDER BY metric_divergencia DESC, m.titulo LIMIT 10
