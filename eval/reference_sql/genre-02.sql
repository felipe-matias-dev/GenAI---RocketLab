SELECT c.nome_produtora AS key_produtora, SUM(f.lucro_usd) AS metric_lucro_total_usd
FROM dim_companies c JOIN bridge_movie_company b USING (sk_company_id)
JOIN fact_movies_performance f USING (sk_movie_id)
WHERE f.receita_usd IS NOT NULL AND f.orcamento_usd IS NOT NULL
GROUP BY c.sk_company_id ORDER BY metric_lucro_total_usd DESC, c.nome_produtora LIMIT 3
