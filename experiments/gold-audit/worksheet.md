# Gold audit worksheet (#99)

Generated from the gold and audit files. It does not confirm anything.
For each row: read the question, read the passage, and decide whether the bold text
really answers the question. For unanswerable rows, decide whether the collection
truly does not contain the answer. Write your verdict in the blank line.

Verdicts: `ok` (correct), `wrong: <why>`, `partial: <why>` (e.g. answer correct but the alias is odd).

## Harbor Institute

### seed-001  (answerable)
- **Question:** What is the North Jetty Teaching Lab's lab code?
- **Gold answers:** `NJ-12`
- **Cited note:** `datasets/corpus/north-jetty-lab.txt`
- **Passage:** North Jetty Teaching Lab booking rules The lab code is **NJ-12**. Undergraduate project groups may book at most one 3-hour slot per day. Slots start at 09:00, 13:00, and 16:30 on weekdays only. A booking is cancelled if no …
- **Your check:** ______________________

### seed-002  (answerable)
- **Question:** Which floor of the Harbor Institute Library is the quiet study floor?
- **Gold answers:** `Level 3` / `3`
- **Cited note:** `datasets/corpus/harbor-library.txt`
- **Passage:** Harbor Institute Library hours (term time) Monday to Thursday: 08:00–21:00 Friday: 08:00–18:00 Saturday: 10:00–16:00 Sunday: closed The quiet study floor is **Level 3**. Group rooms on Level 1 must be booked in the Harbor Desk app at least two hours ahead. Food is not allowed except bottled water. The late-return fine is 2 ha…
- **Your check:** ______________________

### seed-003  (answerable)
- **Question:** What is the campus shuttle called?
- **Gold answers:** `Tideline` / `the Tideline`
- **Cited note:** `datasets/corpus/tideline-shuttle.txt`
- **Passage:** Harbor Institute shuttle loop The campus shuttle is named the **Tideline**. On weekdays it runs every 12 minutes from 07:30 to 19:30. Weekend service is every 25 minutes from 09:00 to 17:00. Stops in order: Gatehouse, Library Plaza, …
- **Your check:** ______________________

### gold-013  (answerable)
- **Question:** What is the South Jetty Teaching Lab's lab code?
- **Gold answers:** `SJ-07`
- **Cited note:** `datasets/corpus/south-jetty-lab.txt`
- **Passage:** South Jetty Teaching Lab booking rules The lab code is **SJ-07**. Undergraduate project groups may book up to two 2-hour slots per day. Slots start at 10:00, 14:00, and 18:00, and the lab does open on Saturdays. A booking i…
- **Your check:** ______________________

### gold-015  (answerable)
- **Question:** Who is the lab manager of the South Jetty Teaching Lab?
- **Gold answers:** `Dev Okonkwo`
- **Cited note:** `datasets/corpus/south-jetty-lab.txt`
- **Passage:** …ith a student card within 10 minutes of the start time. Safety glasses are required at all times inside the wet bench area, powered or not. The lab manager is **Dev Okonkwo** (dev.okonkwo@harbor-institute.example). There is no overnight access at South Jetty under any circumstances; the building is locked at 21:00. 
- **Your check:** ______________________

### gold-024  (answerable)
- **Question:** Who is the lab manager of the North Jetty Teaching Lab?
- **Gold answers:** `Priya Chen`
- **Cited note:** `datasets/corpus/north-jetty-lab.txt`
- **Passage:** …ember taps in with a student card within 15 minutes of the start time. Safety glasses are required whenever the soldering bench is powered. The lab manager is **Priya Chen** (priya.chen@harbor-institute.example). After 18:00, access requires a signed overnight form from the department office. 
- **Your check:** ______________________

### gold-032  (answerable)
- **Question:** What room is the Coastal Memory Group office in?
- **Gold answers:** `Room 214` / `214`
- **Cited note:** `datasets/corpus/coastal-memory-group.txt`
- **Passage:** Coastal Memory Group (fictional research unit) The Coastal Memory Group studies how harbor towns archive storm records. The group office is **Room 214** in the East Archive wing. Weekly seminar: Thursday 16:00–17:00 in Seminar Hut B. Current working corpus (internal nickname: Salt Ledger) contains 48 digitized…
- **Your check:** ______________________

### seed-004  (answerable)
- **Question:** At the North Jetty Teaching Lab, how long is a booking held before it is cancelled if nobody taps in?
- **Gold answers:** `15 minutes` / `15`
- **Cited note:** `datasets/corpus/north-jetty-lab.txt`
- **Passage:** … most one 3-hour slot per day. Slots start at 09:00, 13:00, and 16:30 on weekdays only. A booking is cancelled if no member taps in with a student card within **15 minutes** of the start time. Safety glasses are required whenever the soldering bench is powered. The lab manager is Priya Chen (priya.chen@harbor-institute.example). A…
- **Your check:** ______________________

### seed-005  (answerable)
- **Question:** How many hours did the 1921 Green Lamp Flood last in Harbor Town?
- **Gold answers:** `31 hours` / `31`
- **Cited note:** `datasets/corpus/coastal-memory-group.txt`
- **Passage:** …nterview requests go to memory@harbor-institute.example, not to personal inboxes. The group’s public fact sheet states that the 1921 “Green Lamp Flood” lasted **31 hours** in Harbor Town, not 48. That correction is deliberate; older tourist plaques are wrong. 
- **Your check:** ______________________

### seed-006  (answerable)
- **Question:** What time does the Tide Canteen kitchen close on Fridays?
- **Gold answers:** `19:00` / `7pm` / `7:00 pm`
- **Cited note:** `datasets/corpus/tide-canteen.txt`
- **Passage:** …the canteen serves dumplings only at lunch, 11:30–13:30. The filling is fennel and tofu; no meat option that day. Friday: fish-cake soup. The kitchen closes at **19:00** on Fridays, one hour earlier than other weekdays. Allergy board: sesame is used in the Friday chili oil. The Wednesday dumplings are steamed, not fried. Paym…
- **Your check:** ______________________

### gold-014  (answerable)
- **Question:** At the South Jetty Teaching Lab, how long is a booking held before it is cancelled if nobody taps in?
- **Gold answers:** `10 minutes` / `10`
- **Cited note:** `datasets/corpus/south-jetty-lab.txt`
- **Passage:** …ts per day. Slots start at 10:00, 14:00, and 18:00, and the lab does open on Saturdays. A booking is cancelled if no member taps in with a student card within **10 minutes** of the start time. Safety glasses are required at all times inside the wet bench area, powered or not. The lab manager is Dev Okonkwo (dev.okonkwo@harbor-inst…
- **Your check:** ______________________

### gold-016  (answerable)
- **Question:** How many harbor credits does a standard meal cost at the East Canteen?
- **Gold answers:** `3` / `3 harbor credits` / `3 credits`
- **Cited note:** `datasets/corpus/east-canteen.txt`
- **Passage:** … option. Friday: clam chowder. The East Canteen kitchen closes at 20:00 on Fridays, the same as every other weekday. A standard meal at the East Canteen costs **3** harbor credits; a large portion costs 4. Allergy board: peanuts are used in the Monday braise. The Wednesday dumplings here are pan-fried, not steamed. The E…
- **Your check:** ______________________

### gold-017  (answerable)
- **Question:** What time does the East Canteen kitchen close on Fridays?
- **Gold answers:** `20:00` / `8pm` / `8:00 pm`
- **Cited note:** `datasets/corpus/east-canteen.txt`
- **Passage:** …nesday: dumplings are served at both lunch and dinner. Pork and chive filling, with a mushroom option. Friday: clam chowder. The East Canteen kitchen closes at **20:00** on Fridays, the same as every other weekday. A standard meal at the East Canteen costs 3 harbor credits; a large portion costs 4. Allergy board: peanuts are …
- **Your check:** ______________________

### gold-018  (answerable)
- **Question:** How many digitized station reports does the Storm Ledger Unit hold?
- **Gold answers:** `214`
- **Cited note:** `datasets/corpus/storm-ledger-unit.txt`
- **Passage:** …g. The unit office is Room 108 in the West Archive wing. Weekly seminar: Tuesday 10:00–11:00 in Seminar Hut A. The unit's holdings cover 1940–1975 and include **214** digitized station reports. Records for 1955 are complete and are the unit's most requested series. The unit holds nothing before 1940. Lead archivist: Ana Fer…
- **Your check:** ______________________

### gold-019  (answerable)
- **Question:** How many hours did the 1948 Black Mast Gale last in Harbor Town?
- **Gold answers:** `19 hours` / `19`
- **Cited note:** `datasets/corpus/storm-ledger-unit.txt`
- **Passage:** … Student liaison: Tom Baptiste. Interview requests go to ledger@harbor-institute.example. The unit's fact sheet records that the 1948 "Black Mast Gale" lasted **19 hours** in Harbor Town. The unit does not hold material on the 1921 Green Lamp Flood and refers those enquiries elsewhere. 
- **Your check:** ______________________

### gold-020  (answerable)
- **Question:** How many minutes are there between Tideline runs during winter recess?
- **Gold answers:** `30 minutes` / `30`
- **Cited note:** `datasets/corpus/tideline-winter-recess.txt`
- **Passage:** Tideline shuttle: winter recess schedule During winter recess the Tideline runs a reduced loop: every **30 minutes** from 08:00 to 18:00, every day including weekends. Normal term-time frequencies do not apply during recess. The recess loop skips two stops. Stops served: Gat…
- **Your check:** ______________________

### gold-021  (answerable)
- **Question:** What is the Harbor Institute Library's late-return fine per day?
- **Gold answers:** `2 harbor credits` / `2 credits` / `2`
- **Cited note:** `datasets/corpus/harbor-library.txt`
- **Passage:** …el 3. Group rooms on Level 1 must be booked in the Harbor Desk app at least two hours ahead. Food is not allowed except bottled water. The late-return fine is **2 harbor credits** per day, capped at 40 credits per item. Course reserves cannot leave the building. 
- **Your check:** ______________________

### gold-022  (answerable)
- **Question:** What is the Saltmarsh Annex Library's late-return fine per day?
- **Gold answers:** `1 harbor credit` / `1 credit` / `1`
- **Cited note:** `datasets/corpus/saltmarsh-annex-library.txt`
- **Passage:** …quiet study floor here is Level 2. There are no group rooms; readers who need one should book at the Harbor Desk instead. The late-return fine at the Annex is **1 harbor credit** per day, capped at 25 credits per item. Bottled water and covered cups are both allowed. Annex reserves may be borrowed for 48 hours and may leave the buildin…
- **Your check:** ______________________

### gold-023  (answerable)
- **Question:** Which floor of the Saltmarsh Annex Library is the quiet study floor?
- **Gold answers:** `Level 2` / `2`
- **Cited note:** `datasets/corpus/saltmarsh-annex-library.txt`
- **Passage:** …urday: closed Sunday: 12:00–18:00 The Annex is a separate building from the Harbor Institute Library and keeps its own schedule. The quiet study floor here is **Level 2**. There are no group rooms; readers who need one should book at the Harbor Desk instead. The late-return fine at the Annex is 1 harbor credit per day, capped a…
- **Your check:** ______________________

### seed-011  (answerable)
- **Question:** What are the Saltmarsh Annex Library's Sunday hours?
- **Gold answers:** `12:00-18:00` / `12:00–18:00`
- **Cited note:** `datasets/corpus/saltmarsh-annex-library.txt`
- **Passage:** Saltmarsh Annex Library hours (term time) Monday to Friday: 09:00–17:00 Saturday: closed Sunday: **12:00–18:00** The Annex is a separate building from the Harbor Institute Library and keeps its own schedule. The quiet study floor here is Level 2. There are no group rooms…
- **Your check:** ______________________

### seed-012  (answerable)
- **Question:** What are the Harbor Institute Library's current Saturday hours?
- **Gold answers:** `10:00-16:00` / `10:00–16:00`
- **Cited note:** `datasets/corpus/harbor-library.txt`
- **Passage:** Harbor Institute Library hours (term time) Monday to Thursday: 08:00–21:00 Friday: 08:00–18:00 Saturday: **10:00–16:00** Sunday: closed The quiet study floor is Level 3. Group rooms on Level 1 must be booked in the Harbor Desk app at least two hours ahead. Food is not allowed ex…
- **Your check:** ______________________

### gold-025  (answerable)
- **Question:** What were the Harbor Institute Library's Saturday hours during the 2019 East Wing renovation?
- **Gold answers:** `12:00-15:00` / `12:00–15:00`
- **Cited note:** `datasets/corpus/harbor-library-2019-notice.txt`
- **Passage:** …or current hours see the term-time hours sheet. Renovation hours in effect March–December 2019: Monday to Thursday: 10:00–16:00 Friday: 10:00–14:00 Saturday: **12:00–15:00** Sunday: closed During the renovation the quiet study floor was temporarily moved to Level 1 and no group rooms were available. The late-return fine was suspen…
- **Your check:** ______________________

### seed-007  (NOT answerable)
- **Question:** Which shuttle stop is closest to the boat museum?
- **Why it should be unanswerable (gold note):** Corpus states there is no stop at the boat museum, so the question presupposes something false. Sounds answerable because the museum is mentioned.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### seed-008  (NOT answerable)
- **Question:** What storm records does the Coastal Memory Group hold from 1955?
- **Why it should be unanswerable (gold note):** Corpus says the group holds nothing after 1940. Retrieval will return the relevant document, so sufficiency must be judged on content rather than topical match.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### seed-009  (NOT answerable)
- **Question:** How much does a Tide Canteen meal cost in harbor credits?
- **Why it should be unanswerable (gold note):** Corpus says payment is harbor credits only but never gives a price. Tests the difference between a relevant document and a sufficient one. Contrast with gold-016.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### seed-010  (NOT answerable)
- **Question:** Who is the lab manager of the East Archive wing?
- **Why it should be unanswerable (gold note):** Conflates two documents: lab managers exist (Priya Chen, Dev Okonkwo) and the East Archive wing exists, but not together. Tests spurious cross-document composition.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### gold-026  (NOT answerable)
- **Question:** How many hours did the 1921 Green Lamp Flood last according to the Storm Ledger Unit?
- **Why it should be unanswerable (gold note):** Storm Ledger does not hold Green Lamp Flood material and refers those enquiries elsewhere. Contrast with seed-005. Sounds answerable because both units publish storm durations.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### gold-027  (NOT answerable)
- **Question:** On which dates does Tideline winter recess run this year?
- **Why it should be unanswerable (gold note):** The recess sheet says dates are published by the department office each year and are not listed there. Frequency is stated; dates are not.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### gold-028  (NOT answerable)
- **Question:** At the North Jetty Teaching Lab, are safety glasses required at all times inside the wet bench area?
- **Why it should be unanswerable (gold note):** Wrong-entity trap. Wet-bench glasses are a South Jetty fact. North Jetty discusses a soldering bench, not a wet bench.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### gold-029  (NOT answerable)
- **Question:** How many hours did the 1948 Black Mast Gale last according to the Coastal Memory Group?
- **Why it should be unanswerable (gold note):** Contrast with gold-019. Coastal Memory holds nothing after 1940 and does not document this gale.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### gold-030  (NOT answerable)
- **Question:** How many hours ahead must a group room at the Saltmarsh Annex Library be booked?
- **Why it should be unanswerable (gold note):** False presupposition: the Annex has no group rooms. Harbor Institute Library requires two hours in the Harbor Desk app.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### gold-031  (NOT answerable)
- **Question:** What time does breakfast end at the East Canteen?
- **Why it should be unanswerable (gold note):** Monday breakfast dishes are named; no breakfast end time is given.
- **Check:** search `datasets/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

## Duke Kunshan University

### dku-001  (answerable)
- **Question:** In which month and year was Duke Kunshan University established as a partnership between Duke University and Wuhan University?
- **Gold answers:** `September 2013`
- **Cited note:** `datasets/dku/corpus/dku-about.txt`
- **Passage:** Duke Kunshan University (DKU) is a liberal arts and research university in Kunshan, Jiangsu, China. It was established in **September 2013** as a U.S.-China partnership between Duke University and Wuhan University. DKU welcomed its first students in August 2014, beginning with Duke graduate degrees…
- **Your check:** ______________________

### dku-002  (answerable)
- **Question:** What is Duke Kunshan University's street address?
- **Gold answers:** `No. 8 Duke Avenue` / `8 Duke Avenue`
- **Cited note:** `datasets/dku/corpus/dku-about.txt`
- **Passage:** …ergraduate bachelor's program began in August 2018. The campus covers 200 acres in Kunshan's Yangcheng Lake Science and Technology Park. The street address is **No. 8 Duke Avenue**, Kunshan, Jiangsu Province, China 215316. This note is a short local summary of public facts. It does not list tuition, enrollment headcounts, or the names of…
- **Your check:** ______________________

### dku-003  (answerable)
- **Question:** When did Duke Kunshan University welcome its first students?
- **Gold answers:** `August 2014`
- **Cited note:** `datasets/dku/corpus/dku-about.txt`
- **Passage:** …ngsu, China. It was established in September 2013 as a U.S.-China partnership between Duke University and Wuhan University. DKU welcomed its first students in **August 2014**, beginning with Duke graduate degrees and a Global Learning Semester. The four-year undergraduate bachelor's program began in August 2018. The campus covers 2…
- **Your check:** ______________________

### dku-004  (answerable)
- **Question:** When did Duke Kunshan University's four-year undergraduate bachelor's program begin?
- **Gold answers:** `August 2018`
- **Cited note:** `datasets/dku/corpus/dku-about.txt`
- **Passage:** …its first students in August 2014, beginning with Duke graduate degrees and a Global Learning Semester. The four-year undergraduate bachelor's program began in **August 2018**. The campus covers 200 acres in Kunshan's Yangcheng Lake Science and Technology Park. The street address is No. 8 Duke Avenue, Kunshan, Jiangsu Province, Chin…
- **Your check:** ______________________

### dku-005  (answerable)
- **Question:** How many acres is the Duke Kunshan University campus?
- **Gold answers:** `200 acres` / `200`
- **Cited note:** `datasets/dku/corpus/dku-about.txt`
- **Passage:** …4, beginning with Duke graduate degrees and a Global Learning Semester. The four-year undergraduate bachelor's program began in August 2018. The campus covers **200 acres** in Kunshan's Yangcheng Lake Science and Technology Park. The street address is No. 8 Duke Avenue, Kunshan, Jiangsu Province, China 215316. This note is a shor…
- **Your check:** ______________________

### dku-006  (answerable)
- **Question:** What are the DKU Library building hours Monday through Sunday, according to the current Locations and Hours page?
- **Gold answers:** `08:00-23:00` / `8:00-23:00` / `8:00 – 23:00`
- **Cited note:** `datasets/dku/corpus/dku-library-hours.txt`
- **Passage:** …hours are the current regular schedule published on the DKU Library website. Holiday hours are announced separately and are not listed here. Library building: **08:00-23:00**, Monday through Sunday. 1st floor information desk: Monday-Friday: 09:00-21:00 Saturday-Sunday: 14:00-21:00 DVD and equipment loan: Monday-Friday, 09:00-17:3…
- **Your check:** ______________________

### dku-007  (answerable)
- **Question:** According to the current DKU Library Locations and Hours page, what are the 1st floor information desk hours on Saturday?
- **Gold answers:** `14:00-21:00` / `14:00 – 21:00`
- **Cited note:** `datasets/dku/corpus/dku-library-hours.txt`
- **Passage:** …rately and are not listed here. Library building: 08:00-23:00, Monday through Sunday. 1st floor information desk: Monday-Friday: 09:00-21:00 Saturday-Sunday: **14:00-21:00** DVD and equipment loan: Monday-Friday, 09:00-17:30. Contact: (+86) 0512-36658756 (Monday-Friday, 09:00-17:00) dkulibrary@dukekunshan.edu.cn No. 8 Duke Avenue…
- **Your check:** ______________________

### dku-008  (answerable)
- **Question:** According to the January 2025 DKU Library Guide, what are the 1st floor information desk hours on Saturday?
- **Gold answers:** `14:00-18:00` / `14:00 – 18:00`
- **Cited note:** `datasets/dku/corpus/dku-library-guide-202501.txt`
- **Passage:** …ide lists 23 self and group study rooms and 560 seats. 1st floor information desk in this brochure: Monday-Thursday: 09:00-21:00 Friday: 09:00-17:30 Saturday: **14:00-18:00** Sunday: 14:00-20:00 The Tea House is on the 3rd floor and connects to a sky garden. The Meditation Room is on the 4th floor (LIB4-16) and looks over the Acade…
- **Your check:** ______________________

### dku-009  (answerable)
- **Question:** How many seats does the January 2025 DKU Library Guide list?
- **Gold answers:** `560`
- **Cited note:** `datasets/dku/corpus/dku-library-guide-202501.txt`
- **Passage:** …is brochure as dated January 2025. Library building: Monday-Sunday 08:00-23:00. Side gates use swipe access. The guide lists 23 self and group study rooms and **560** seats. 1st floor information desk in this brochure: Monday-Thursday: 09:00-21:00 Friday: 09:00-17:30 Saturday: 14:00-18:00 Sunday: 14:00-20:00 The Tea House …
- **Your check:** ______________________

### dku-010  (answerable)
- **Question:** According to the January 2025 DKU Library Guide, which floor is the Tea House on?
- **Gold answers:** `3rd floor` / `3rd` / `Level 3` / `3`
- **Cited note:** `datasets/dku/corpus/dku-library-guide-202501.txt`
- **Passage:** …st floor information desk in this brochure: Monday-Thursday: 09:00-21:00 Friday: 09:00-17:30 Saturday: 14:00-18:00 Sunday: 14:00-20:00 The Tea House is on the **3rd floor** and connects to a sky garden. The Meditation Room is on the 4th floor (LIB4-16) and looks over the Academic Quad. Source: https://library.dukekunshan.edu.cn/w…
- **Your check:** ______________________

### dku-011  (answerable)
- **Question:** What are DVD and equipment loan hours at the DKU Library according to the current Locations and Hours page?
- **Gold answers:** `09:00-17:30` / `9:00-17:30`
- **Cited note:** `datasets/dku/corpus/dku-library-hours.txt`
- **Passage:** …8:00-23:00, Monday through Sunday. 1st floor information desk: Monday-Friday: 09:00-21:00 Saturday-Sunday: 14:00-21:00 DVD and equipment loan: Monday-Friday, **09:00-17:30**. Contact: (+86) 0512-36658756 (Monday-Friday, 09:00-17:00) dkulibrary@dukekunshan.edu.cn No. 8 Duke Avenue, Kunshan, Jiangsu Province, China 215316 This page…
- **Your check:** ______________________

### dku-012  (answerable)
- **Question:** What email does the current DKU Library Locations and Hours page list?
- **Gold answers:** `dkulibrary@dukekunshan.edu.cn`
- **Cited note:** `datasets/dku/corpus/dku-library-hours.txt`
- **Passage:** …riday: 09:00-21:00 Saturday-Sunday: 14:00-21:00 DVD and equipment loan: Monday-Friday, 09:00-17:30. Contact: (+86) 0512-36658756 (Monday-Friday, 09:00-17:00) **dkulibrary@dukekunshan.edu.cn** No. 8 Duke Avenue, Kunshan, Jiangsu Province, China 215316 This page is about the Kunshan campus library. It is not Duke University Libraries in Durham, North…
- **Your check:** ______________________

### dku-013  (answerable)
- **Question:** According to the August 2021 DKU student handbook, what phone number is listed for the DKU Library?
- **Gold answers:** `(0512) 3665-7027` / `0512-3665-7027` / `3665-7027`
- **Cited note:** `datasets/dku/corpus/dku-library-handbook-2021.txt`
- **Passage:** … In this 2021 handbook, the DKU Library is described as occupying two rooms on the first and second floor of the Academic Building. The listed phone number is **(0512) 3665-7027**. The listed email is dkulibrary@dukekunshan.edu.cn. The handbook also mentions a joint service relationship with Duke University Libraries (DUL). Do not use t…
- **Your check:** ______________________

### dku-014  (answerable)
- **Question:** According to the August 2021 DKU student handbook, where is the DKU Library located?
- **Gold answers:** `Academic Building` / `two rooms in the Academic Building`
- **Cited note:** `datasets/dku/corpus/dku-library-handbook-2021.txt`
- **Passage:** …scribe the current dedicated library building. In this 2021 handbook, the DKU Library is described as occupying two rooms on the first and second floor of the **Academic Building**. The listed phone number is (0512) 3665-7027. The listed email is dkulibrary@dukekunshan.edu.cn. The handbook also mentions a joint service relationship with D…
- **Your check:** ______________________

### dku-015  (answerable)
- **Question:** What are breakfast hours at University Dining in the Academic Building?
- **Gold answers:** `07:00-09:30` / `7:00-9:30`
- **Cited note:** `datasets/dku/corpus/academic-building-dining.txt`
- **Passage:** …s on campus serve Chinese, Western, and Halal dishes. This note covers only the two Academic Building venues. University Dining @ Academic Building: Breakfast **07:00-09:30** Lunch 11:00-13:30 Dinner 17:00-19:30 Executive Dining @ Academic Building: Lunch 11:00-13:30 No breakfast hours and no dinner hours are listed for Executive D…
- **Your check:** ______________________

### dku-016  (answerable)
- **Question:** What are lunch hours at Executive Dining in the Academic Building?
- **Gold answers:** `11:00-13:30`
- **Cited note:** `datasets/dku/corpus/academic-building-dining.txt`
- **Passage:** …Chinese, Western, and Halal dishes. This note covers only the two Academic Building venues. University Dining @ Academic Building: Breakfast 07:00-09:30 Lunch **11:00-13:30** Dinner 17:00-19:30 Executive Dining @ Academic Building: Lunch 11:00-13:30 No breakfast hours and no dinner hours are listed for Executive Dining. This note …
- **Your check:** ______________________

### dku-017  (answerable)
- **Question:** What are dinner hours at Halal Dining at the Conference Center?
- **Gold answers:** `17:00-19:30`
- **Cited note:** `datasets/dku/corpus/conference-center-dining.txt`
- **Passage:** Campus dining — Conference Center Halal Dining Halal Dining @ Conference Center: Lunch 11:00-13:30 Dinner **17:00-19:30** No breakfast hours are listed for Halal Dining at the Conference Center. This venue is not University Dining in the Academic Building. It does not list price…
- **Your check:** ______________________

### dku-018  (answerable)
- **Question:** On what date do undergraduate and graduate classes begin in Fall 2026 at Duke Kunshan University?
- **Gold answers:** `24 August 2026` / `August 24, 2026` / `August 24 2026`
- **Cited note:** `datasets/dku/corpus/registrar-fall-2026.txt`
- **Passage:** DKU Registrar — Fall 2026 dates Undergraduate and graduate classes begin Monday, **24 August 2026**. New international undergraduate students (Class of 2030) and international first-year graduate students move in Friday, 14 August 2026 at 09:00. New Chinese …
- **Your check:** ______________________

### dku-019  (answerable)
- **Question:** On what date do DKU residence halls close for Winter Break in Fall 2026?
- **Gold answers:** `18 December 2026` / `December 18, 2026` / `December 18 2026`
- **Cited note:** `datasets/dku/corpus/registrar-fall-2026.txt`
- **Passage:** … 12 October 2026. Mid-Autumn Festival: no classes Friday 25 September through Sunday 27 September 2026. All residence halls close for Winter Break on Friday, **18 December 2026** at 13:00. Holiday hours for the library are not listed on this registrar page. Source: https://registrar.dukekunshan.edu.cn/academic-calendar/ (retrieved 202…
- **Your check:** ______________________

### dku-020  (answerable)
- **Question:** On what date is graduate and undergraduate commencement at Duke Kunshan University in Spring 2027?
- **Gold answers:** `21 May 2027` / `May 21, 2027` / `May 21 2027`
- **Cited note:** `datasets/dku/corpus/registrar-spring-2027.txt`
- **Passage:** … no classes Friday 5 February 2027 through Sunday 14 February 2027. Classes resume Monday 15 February 2027. Graduate and undergraduate commencement is Friday, **21 May 2027**. All residence halls close Saturday, 22 May 2027 at 13:00. Qing Ming (Tomb Sweeping Day): no classes Monday 5 April 2027. This page does not list tuition, di…
- **Your check:** ______________________

### dku-021  (answerable)
- **Question:** How far is Kunshan South Railway Station from Duke Kunshan University according to the commencement visitor guide?
- **Gold answers:** `12 kilometers` / `12 km` / `12 kilometres`
- **Cited note:** `datasets/dku/corpus/getting-to-dku.txt`
- **Passage:** …l Airport (SHA) is 42 kilometers east of Kunshan. Sunan Shuofang International Airport (WUX) is 41 kilometers west of Kunshan. Kunshan South Railway Station is **12 kilometers** southeast of Duke Kunshan. From Kunshan South Station, a taxi to campus is described as costing around 30 RMB (from the International Students Zone pre-arriva…
- **Your check:** ______________________

### dku-022  (answerable)
- **Question:** How far is Shanghai Pudong International Airport from Kunshan according to the commencement visitor guide?
- **Gold answers:** `92 kilometers` / `92 km` / `92 kilometres`
- **Cited note:** `datasets/dku/corpus/getting-to-dku.txt`
- **Passage:** Getting to Duke Kunshan University Shanghai Pudong International Airport (PVG) is **92 kilometers** east of Kunshan. Shanghai Hongqiao International Airport (SHA) is 42 kilometers east of Kunshan. Sunan Shuofang International Airport (WUX) is 41 kilometers we…
- **Your check:** ______________________

### dku-023  (answerable)
- **Question:** About how much does a taxi from Kunshan South Station to the DKU campus cost according to the International Students Zone note?
- **Gold answers:** `30 RMB` / `around 30 RMB` / `30 yuan`
- **Cited note:** `datasets/dku/corpus/getting-to-dku.txt`
- **Passage:** …Kunshan. Kunshan South Railway Station is 12 kilometers southeast of Duke Kunshan. From Kunshan South Station, a taxi to campus is described as costing around **30 RMB** (from the International Students Zone pre-arrival note). This note does not publish a current weekday campus-shuttle timetable from Kunshan South, and it does…
- **Your check:** ______________________

### dku-024  (answerable)
- **Question:** How far is Dayu Bay from the DKU campus according to the commencement visitor guide?
- **Gold answers:** `500 meters` / `500 metres` / `500 m`
- **Cited note:** `datasets/dku/corpus/dayu-bay.txt`
- **Passage:** Dayu Bay commercial center Dayu Bay is a short walk from the DKU campus. The commencement visitor guide gives the walking distance as **500 meters**. Visitors may park for free in the Dayu Bay commercial center parking lot. The guide says an array of restaurants is located there. This local note does not n…
- **Your check:** ______________________

### dku-025  (answerable)
- **Question:** In what year was the Ziqiang Institute, later connected with Wuhan University, founded?
- **Gold answers:** `1893`
- **Cited note:** `datasets/dku/corpus/wuhan-university.txt`
- **Passage:** …versity. It is not in Kunshan and is not the DKU library, dining halls, or registrar. Wuhan University's history is traced to the Ziqiang Institute founded in **1893** by Zhang Zhidong. In 1928 the institute was renamed Wuhan National University. This note does not list DKU class dates, DKU library hours, or Wuhan University…
- **Your check:** ______________________

### dku-026  (answerable)
- **Question:** In what year did the institution officially become Duke University?
- **Gold answers:** `1924`
- **Cited note:** `datasets/dku/corpus/duke-university-durham.txt`
- **Passage:** …ersity's home campus is in Durham, North Carolina, United States, on nearly 9,000 acres. Duke traces its roots to 1838 and officially became Duke University in **1924**. Duke enrolls more than 15,000 students in undergraduate, graduate, and professional programs. Duke University Libraries (including Perkins and Bostock on Wes…
- **Your check:** ______________________

### dku-027  (answerable)
- **Question:** Up to how many guests does the DKU Conference Center auditorium hold?
- **Gold answers:** `300`
- **Cited note:** `datasets/dku/corpus/conference-center.txt`
- **Passage:** …Conference Center The Conference Center is on the DKU campus in Kunshan. It has over 200 guest rooms, a gym, and on-campus parking. The auditorium holds up to **300** guests. The grand ballroom can be divided into two rooms. Dining venues named for Conference Center guests include the Conference Center Restaurant, Executive…
- **Your check:** ______________________

### dku-028  (answerable)
- **Question:** How many guest rooms does the DKU Conference Center have?
- **Gold answers:** `over 200` / `200` / `more than 200`
- **Cited note:** `datasets/dku/corpus/conference-center.txt`
- **Passage:** Duke Kunshan University Conference Center The Conference Center is on the DKU campus in Kunshan. It has **over 200** guest rooms, a gym, and on-campus parking. The auditorium holds up to 300 guests. The grand ballroom can be divided into two rooms. Dining venues named for Co…
- **Your check:** ______________________

### dku-029  (answerable)
- **Question:** What is the email address for the Center for the Study of Contemporary China at Duke Kunshan University?
- **Gold answers:** `dku-cscc@dukekunshan.edu.cn`
- **Cited note:** `datasets/dku/corpus/cscc.txt`
- **Passage:** …udy of Contemporary China (当代中国研究中心) is at Duke Kunshan University, No. 8 Duke Avenue, Kunshan, Jiangsu Province, China 215316. Phone: +86 512 36657053 Email: **dku-cscc@dukekunshan.edu.cn** CSCC awards a Student-Initiated Research and Creative Inquiry Grant. In Spring 2026 that grant supported Quantitative Political Economy student Tianyi Xie (Cl…
- **Your check:** ______________________

### dku-030  (answerable)
- **Question:** What phone number is listed for the Center for the Study of Contemporary China?
- **Gold answers:** `+86 512 36657053` / `0512 36657053` / `36657053`
- **Cited note:** `datasets/dku/corpus/cscc.txt`
- **Passage:** …) The Center for the Study of Contemporary China (当代中国研究中心) is at Duke Kunshan University, No. 8 Duke Avenue, Kunshan, Jiangsu Province, China 215316. Phone: **+86 512 36657053** Email: dku-cscc@dukekunshan.edu.cn CSCC awards a Student-Initiated Research and Creative Inquiry Grant. In Spring 2026 that grant supported Quantitative Polit…
- **Your check:** ______________________

### dku-031  (NOT answerable)
- **Question:** What time does breakfast end at Halal Dining at the Conference Center?
- **Why it should be unanswerable (gold note):** Halal Dining lists lunch and dinner only. Sounds answerable because University Dining does serve breakfast.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-032  (NOT answerable)
- **Question:** What time does breakfast end at Executive Dining in the Academic Building?
- **Why it should be unanswerable (gold note):** Executive Dining lists lunch only.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-033  (NOT answerable)
- **Question:** What are Perkins Library Saturday hours at Duke University in Durham?
- **Why it should be unanswerable (gold note):** Durham doc exists but lists no Perkins hours. Pretraining leakage trap.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-034  (NOT answerable)
- **Question:** Which restaurant in Dayu Bay is closest to the DKU campus?
- **Why it should be unanswerable (gold note):** Dayu Bay is named; no restaurant names.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-035  (NOT answerable)
- **Question:** What is the current weekday shuttle timetable from Kunshan South Station to the DKU campus?
- **Why it should be unanswerable (gold note):** Taxi fare is stated; no timetable.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-036  (NOT answerable)
- **Question:** What is DKU undergraduate tuition for 2026-2027?
- **Why it should be unanswerable (gold note):** Not in the local corpus. Model may still guess from pretraining.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-037  (NOT answerable)
- **Question:** Who is the current chancellor of Duke Kunshan University?
- **Why it should be unanswerable (gold note):** Officers are omitted on purpose. Leakage trap.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-038  (NOT answerable)
- **Question:** How many undergraduates did Duke Kunshan University enroll in Fall 2023?
- **Why it should be unanswerable (gold note):** Headcounts omitted. Wikipedia-style leakage trap.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-039  (NOT answerable)
- **Question:** What are the DKU Library building hours during Chinese New Year 2027?
- **Why it should be unanswerable (gold note):** Current page says holiday hours are announced separately.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### dku-040  (NOT answerable)
- **Question:** How much does a standard meal cost at University Dining in the Academic Building?
- **Why it should be unanswerable (gold note):** Hours are listed; prices are not. Same trap as Harbor Tide Canteen.
- **Check:** search `datasets/dku/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

## Kestrel Aero Components

### ka-001  (answerable)
- **Question:** Which building at Kestrel Aero machines titanium bulkheads?
- **Gold answers:** `Hangar 2`
- **Cited note:** `datasets/kestrel-aero/corpus/about.txt`
- **Passage:** …Aero Components — about (fictional shop) Kestrel Aero Components is a made-up job shop in the invented town of Red Mesa. It is not a real aerospace supplier. **Hangar 2** machines titanium. Shop 6 machines aluminum. The traveler office is in Hangar 2, bay C. 
- **Your check:** ______________________

### ka-002  (answerable)
- **Question:** What is the active titanium lot on mill M-40?
- **Gold answers:** `KX-441`
- **Cited note:** `datasets/kestrel-aero/corpus/hangar-2.txt`
- **Passage:** Hangar 2 titanium cell Hangar 2 cuts titanium bulkheads on mill M-40. Active lot for the current order is **KX-441**. Coolant is the titanium-only tank, not the aluminum tank from Shop 6. Food is banned on the Hangar 2 floor. 
- **Your check:** ______________________

### ka-003  (answerable)
- **Question:** What AMS specification letter does the 2025 traveler require for titanium plate?
- **Gold answers:** `AMS 4911R` / `4911R`
- **Cited note:** `datasets/kestrel-aero/corpus/traveler-2025.txt`
- **Passage:** Titanium traveler — 2025 issue Titanium plate must be **AMS 4911R**. The 2025 traveler rejects AMS 4911N. Heat-treat condition: annealed. This 2025 issue is the current traveler for Hangar 2 titanium jobs. 
- **Your check:** ______________________

### ka-004  (answerable)
- **Question:** What AMS specification did the 2018 titanium traveler call for?
- **Gold answers:** `AMS 4911N` / `4911N`
- **Cited note:** `datasets/kestrel-aero/corpus/traveler-2018.txt`
- **Passage:** Titanium traveler — 2018 issue (obsolete) The 2018 traveler called for **AMS 4911N**. That letter is obsolete. Keep this sheet only as a dated distractor. Do not use AMS 4911N on current Hangar 2 jobs. 
- **Your check:** ______________________

### ka-005  (answerable)
- **Question:** What are Shift A hours at Kestrel Aero?
- **Gold answers:** `06:00-14:30`
- **Cited note:** `datasets/kestrel-aero/corpus/shifts.txt`
- **Passage:** Shift board Shift A: **06:00-14:30**. Shift B: 14:30-23:00. There is no third shift. The tool crib is staffed on Shift A only. 
- **Your check:** ______________________

### ka-006  (answerable)
- **Question:** Which quality standard is Kestrel registered to?
- **Gold answers:** `AS9100D`
- **Cited note:** `datasets/kestrel-aero/corpus/quality.txt`
- **Passage:** Quality registration Kestrel is registered to **AS9100D**. It is not registered to ISO 13485. The quality office is the glass room in Hangar 2. 
- **Your check:** ______________________

### ka-007  (answerable)
- **Question:** When is micrometer set T-7 due for calibration?
- **Gold answers:** `1 November 2026` / `November 1, 2026`
- **Cited note:** `datasets/kestrel-aero/corpus/calibration.txt`
- **Passage:** Calibration calendar Micrometer set T-7 is due **1 November 2026**. CMM C-2 is due 15 January 2027. The calendar does not list a calibration vendor price. 
- **Your check:** ______________________

### ka-008  (answerable)
- **Question:** Which dock do finished titanium parts leave from?
- **Gold answers:** `Dock West`
- **Cited note:** `datasets/kestrel-aero/corpus/shipping.txt`
- **Passage:** Shipping dock Finished titanium parts leave **Dock West**. Aluminum leaves Dock East. The dock does not accept customer pickup after 16:00. 
- **Your check:** ______________________

### ka-009  (answerable)
- **Question:** Which lot is named on open NCR-88?
- **Gold answers:** `AL-902`
- **Cited note:** `datasets/kestrel-aero/corpus/ncr-log.txt`
- **Passage:** Open nonconformance log (redacted) NCR-88 is an open scratch on lot **AL-902** in Shop 6. No open NCR is listed for lot KX-441. Costs and customer names are omitted. 
- **Your check:** ______________________

### ka-010  (answerable)
- **Question:** What is the traveler desk phone number?
- **Gold answers:** `555-2201`
- **Cited note:** `datasets/kestrel-aero/corpus/contacts.txt`
- **Passage:** Kestrel contacts Traveler desk: **555-2201**. Quality office: 555-2202. Email: travelers@kestrel-aero.example Officer names are omitted on purpose. 
- **Your check:** ______________________

### ka-011  (answerable)
- **Question:** Does Shop 6 cut titanium?
- **Gold answers:** `no` / `does not cut titanium`
- **Cited note:** `datasets/kestrel-aero/corpus/shop-6.txt`
- **Passage:** Shop 6 aluminum cell Shop 6 cuts aluminum fittings on mill M-11. Active lot is AL-902. Shop 6 does **no**t cut titanium and does not store lot KX-441. 
- **Your check:** ______________________

### ka-012  (answerable)
- **Question:** Where do aluminum end mills live?
- **Gold answers:** `Shop 6, drawer 4` / `drawer 4`
- **Cited note:** `datasets/kestrel-aero/corpus/tool-crib.txt`
- **Passage:** Tool crib The crib issues 1/2-inch titanium end mills only on Shift A. After 14:30, mills are locked. Aluminum end mills live in **Shop 6, drawer 4**. 
- **Your check:** ______________________

### ka-013  (NOT answerable)
- **Question:** What is the unit price of a Kestrel bulkhead?
- **Why it should be unanswerable (gold note):** Prices omitted.
- **Check:** search `datasets/kestrel-aero/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### ka-014  (NOT answerable)
- **Question:** Who owns Kestrel Aero Components?
- **Why it should be unanswerable (gold note):** Names omitted.
- **Check:** search `datasets/kestrel-aero/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### ka-015  (NOT answerable)
- **Question:** What ITAR exemption number does Kestrel hold?
- **Why it should be unanswerable (gold note):** Omitted.
- **Check:** search `datasets/kestrel-aero/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________

### ka-016  (NOT answerable)
- **Question:** What does Fay Aerospace charge per hour?
- **Why it should be unanswerable (gold note):** Sister shop, no rates.
- **Check:** search `datasets/kestrel-aero/corpus/` for the answer and confirm it is absent.
- **Your check:** ______________________
