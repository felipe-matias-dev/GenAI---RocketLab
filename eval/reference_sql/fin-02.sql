SELECT g.nome_genero AS key_genero, AVG(f.lucro_usd) AS metric_lucro_medio_usd
FROM fact_movies_performance f
JOIN bridge_movie_genre b USING (sk_movie_id) JOIN dim_genres g USING (sk_genre_id)
WHERE f.receita_usd IS NOT NULL
GROUP BY g.sk_genre_id ORDER BY metric_lucro_medio_usd DESC
