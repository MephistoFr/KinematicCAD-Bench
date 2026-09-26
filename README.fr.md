# KinematicCAD-Bench

Un banc d’essai exécutable pour évaluer la conception mécanique par IA, sans LLM évaluateur.
Le code produit un verdict à partir de solides B-Rep, d’opérations booléennes et de trajectoires
issues d’un moteur physique réel.

```bash
uv sync --frozen --extra dev
uv run kcb demo --family slider_crank --unsafe-local --out runs/demo
```

Ouvrir `runs/demo/evaluation/evidence.html` : le mécanisme est consultable en 3D, image par image,
sans connexion Internet. Des GIFs, un PNG, les séries temporelles et le modèle physique sont aussi
enregistrés. Ce mode local est réservé aux scripts de confiance et exclu du classement officiel.
Pour les réponses générées par un modèle, utiliser les deux images Docker décrites dans le README.

Les cinq familles sont le guidage linéaire, les engrenages extérieurs, la bielle-manivelle,
la came excentrique et le train épicycloïdal. Chaque contrat impose les axes, les charges, les
tolérances et une relation analytique entrée/sortie. Le juge calcule les masses et les inerties
depuis la CAO. Les rapports d’engrenages ne sont jamais imposés artificiellement au moteur.

Les critères sont cumulatifs : topologie valide, absence d’interpénétration au repos, jeux
fonctionnels, transmission mesurée sous charge, stabilité des liaisons, convergence avec un
pas de temps divisé par deux, puis preuve visuelle autonome. Un échec ne peut pas être compensé
par une bonne note sur un autre critère.

La version 0.1 est une base de recherche fonctionnelle. Elle fournit des tâches publiques de
calibration, des conceptions de référence, des contre-exemples et des tests automatisés. Elle
ne prétend pas démontrer l’absence de contamination, l’identité bit à bit entre processeurs
différents, ni la résistance réelle des pièces fabriquées. Le protocole documente précisément
ces limites et les conditions de publication d’un classement.

Consulter le [README complet](README.md), le [protocole scientifique](docs/PROTOCOL.md),
l’[architecture](docs/ARCHITECTURE.md) et le [guide de contribution](CONTRIBUTING.md).

