SELECT m.titulo AS key_titulo, ABS(r.nota_media_usuarios - f.nota_imdb) AS metric_divergencia
FROM dim_movies m JOIN dim_reviews r USING (sk_movie_id)
JOIN fact_movies_performance f USING (sk_movie_id)
WHERE r.nota_media_usuarios IS NOT NULL AND f.nota_imdb IS NOT NULL
ORDER BY metric_divergencia DESC, m.titulo LIMIT 10
