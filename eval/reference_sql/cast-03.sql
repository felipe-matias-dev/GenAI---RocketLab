WITH direcoes AS MATERIALIZED (
  SELECT b.sk_movie_id, b.sk_person_id FROM dim_people p
  JOIN bridge_movie_person b USING (sk_person_id) WHERE p.tipo_pessoa = 'Diretor'
), pares AS (
  SELECT b.sk_person_id AS ator_id, d.sk_person_id AS diretor_id, COUNT(*) AS filmes
  FROM direcoes d CROSS JOIN bridge_movie_person b ON b.sk_movie_id = d.sk_movie_id
  GROUP BY b.sk_person_id, d.sk_person_id
)
SELECT a.nome_pessoa AS key_ator, d.nome_pessoa AS key_diretor, p.filmes AS metric_filmes
FROM pares p JOIN dim_people a ON a.sk_person_id = p.ator_id
JOIN dim_people d ON d.sk_person_id = p.diretor_id
WHERE a.tipo_pessoa = 'Ator'
ORDER BY p.filmes DESC, a.nome_pessoa, d.nome_pessoa LIMIT 3
