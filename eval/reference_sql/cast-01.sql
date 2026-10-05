SELECT p.nome_pessoa AS key_ator, COUNT(DISTINCT m.sk_movie_id) AS metric_filmes
FROM dim_movies m JOIN bridge_movie_person b USING (sk_movie_id)
JOIN dim_people p USING (sk_person_id)
WHERE p.tipo_pessoa = 'Ator'
  AND m.data_lancamento BETWEEN date('now', '-5 years') AND date('now')
GROUP BY p.sk_person_id ORDER BY metric_filmes DESC, p.nome_pessoa LIMIT 6
