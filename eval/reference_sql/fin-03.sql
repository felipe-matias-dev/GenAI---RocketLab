SELECT m.titulo AS key_titulo,
       100.0 * (f.receita_usd - f.orcamento_usd) / f.receita_usd AS metric_margem
FROM dim_movies m JOIN fact_movies_performance f USING (sk_movie_id)
WHERE f.receita_usd > 0 AND f.orcamento_usd IS NOT NULL
ORDER BY metric_margem DESC, m.titulo LIMIT 10
