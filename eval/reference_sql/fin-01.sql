SELECT m.titulo AS key_titulo, f.receita_brl AS metric_receita_brl
FROM dim_movies m JOIN fact_movies_performance f USING (sk_movie_id)
WHERE f.receita_brl IS NOT NULL
ORDER BY f.receita_brl DESC, m.titulo LIMIT 15
