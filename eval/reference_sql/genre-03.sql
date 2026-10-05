SELECT g.nome_genero AS key_genero,
       AVG(100.0 * (f.receita_usd - f.orcamento_usd) / f.receita_usd) AS metric_margem_media
FROM fact_movies_performance f
JOIN bridge_movie_genre b USING (sk_movie_id) JOIN dim_genres g USING (sk_genre_id)
WHERE f.receita_usd > 0 AND f.orcamento_usd IS NOT NULL
GROUP BY g.sk_genre_id ORDER BY metric_margem_media DESC LIMIT 6
