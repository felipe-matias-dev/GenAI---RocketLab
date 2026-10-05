SELECT m.titulo AS key_titulo, r.qtd_avaliacoes_usuarios AS metric_qtd
FROM dim_movies m JOIN dim_reviews r USING (sk_movie_id)
WHERE r.qtd_avaliacoes_usuarios IS NOT NULL
ORDER BY r.qtd_avaliacoes_usuarios DESC, m.titulo LIMIT 10
