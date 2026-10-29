# Is beating the bookies really possible?

I read "10 equations that rule the world" and was very intrigued by the idea of automating and successfully winning sports bets. It didn’t seem like it would work, but it was a cool problem to solve, so I tried it with the 2026 World Cup (knowing nothing about football or betting).
I followed the author's instructions from here to calculate the alpha and beta values to feed into the equation. I scoured the internet for past datasets and historical closing odds and eventually my model was ready.
This equation doesn’t predict who will win the match, but instead the alpha and beta are calculated to adjust for how bookmakers adjust the odds to make a profit. With that in mind the equation then works with ‘fair’ odds to determine value bets that are mathematically worth placing.
I equipped myself with a subscription to get up to date odds from UK bookmakers (the closer to the match the final calculation is ran and the bet placed the higher the likelihood of finding a value bet).

## Here’s what I learned:
- this approach needs volume
- In this case it turned out that value bets could be identified just as accurately if the bet way places within 12 hours of the match meaning that I missed out on some, because staying up until 2 am appealing
- As a total beginner to both betting of any kind and football I misunderstood how some of the odds were quoted and lost bets were the backed team won, but in extra time
- This experiment was limited to £100 and surprisingly I did well enough that after initial losses I recovered almost the full amount, but then proceeded to lose most of it due to the mistakes listed above
- Overall this was good fun and I learned a lot of cool things


## To run

1. 1_fetch_calibration_data.py — in this case fetches historical Pinnacle odds + scores for WC 2022, Euro 2020/2024, Copa 2024 → 191 matches in international_odds_calibration.csv
2. 2_plot_betting.py — fits α and β via GLM on that data → α=0.943, β=0.698 (closing odds, p=0.007, statistically significant)
3. 3_fetch_wc2026_odds.py — fetches live WC 2026 Pinnacle + soft bookmaker odds → wc2026_odds.csv
4. 4_model.py — reads those odds, applies the model, prints two sections:
  - Section 1: model fair odds vs Pinnacle (small edges, model signal)
  - Section 2: model fair odds vs Bet365/Unibet etc. (larger edges where soft books are slow)

