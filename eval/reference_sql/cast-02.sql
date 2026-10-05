SELECT p.nome_pessoa AS key_diretor, AVG(f.nota_imdb) AS metric_nota_media
FROM dim_people p JOIN bridge_movie_person b USING (sk_person_id)
JOIN fact_movies_performance f USING (sk_movie_id)
WHERE p.tipo_pessoa = 'Diretor' AND f.nota_imdb IS NOT NULL
GROUP BY p.sk_person_id HAVING COUNT(*) >= 5
ORDER BY metric_nota_media DESC, p.nome_pessoa LIMIT 15
