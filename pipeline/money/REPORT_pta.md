# PTA matching report

Generated 2026-11-07 by `pipeline/money/pta.py` (seed 1, 61s).

- Candidate charities (main, parents' association by name): 14,126
- Wider-name candidates (Friends of X, P.T.A., Parent/Teacher, Families & Staff, Supporters of; rules f and d only): 6,533, of which 820 matched to 811 schools
- Schools matched: 10,230
- Charities matched: 10,859 (272 shared infant/junior attributions)
- By method: address-town 16, council-unique 2,190, domain 292, objects 20, postcode 6,178, postcode-exact 1,424, predecessor 302, sector 370, website 67
- Pass-2 rules agreeing (a charity can count under several): address-town 379, council-unique 2,341, domain 904, objects 445, postcode-exact 1,424, predecessor 382
- Pass-1 ambiguity rejections: 680
- Ambiguous charities exported for adjudication: 1,455 (flagged_single_fit 442, partial_name 352, several_fit 441, single_fit_blocked 220)
- Merged from the adjudicator (llm): 0; from the website crawl: 0
- Adjudicator answers in pta_llm.json: 1,448, 640 accepted, 14 'shared:'; gate: no spot check recorded (pta_adjudicate.py sample, then spot-check)
- Website crawl hits confirming an existing match (evidence gains 'website'): 0
- Annual return Part A attached: 6,293 of 10,859 matched charities
- history_status of matched charities: current 8,137, recent 441, historical 2,281
- Schools by their most recent PTA: current 8,080, recent 398, historical 1,752 (current = income for a year ending 2024 or later, recent = since 2019)

## 25 random `postcode` matches for review

| school | charity | evidence |
|---|---|---|
| Loose Primary School | LOOSE PRIMARY SCHOOL PARENT AND TEACHER ASSOCIATION (1023767) | tokens loose; postcode ME159UW |
| Scarcroft Primary School | FRIENDS OF SCARCROFT SCHOOL (1150551) | tokens scarcroft; postcode YO231BS |
| Thornton Primary School | THORNTON PRIMARY PTFA (517320) | tokens thornton; postcode FY54JP |
| Pyrford Church of England Primary School | FRIENDS OF PYRFORD PRIMARY SCHOOL (1047320) | tokens pyrford; postcode GU228SP |
| Cooper's Lane Primary School | COOPERS LANE PARENT TEACHERS ASSOCIATION (1017537) | tokens cooper,lane; postcode SE120LF |
| Digby Church of England School | FRIENDS OF DIGBY SCHOOL PTA (1114295) | tokens digby; postcode LN43LZ |
| Layfield Primary School | FRIENDS OF LAYFIELD PRIMARY SCHOOL (1102861) | tokens layfield; postcode TS159TF |
| George Street Primary School | FRIENDS OF GEORGE STREET SCHOOL (1108071) | tokens george,street; postcode HP25HJ |
| Darley Dale Primary School | DARLEY DALE PRIMARY PTA (1186492) | tokens darley,dale; postcode DE42QB |
| Overbury CofE First School | FRIENDS OF OVERBURY SCHOOL (1088734) | tokens overbury; postcode GL207NT |
| Vigo Village School | PARENTS, TEACHERS, AND FRIENDS OF VIGO VILLAGE SCHOOL (1041219) | tokens vigo,village; postcode DA130RL |
| Whitefriars Church of England Primary Academy | WHITEFRIARS PARENT SCHOOL ASSOCIATION (1007104) | tokens whitefriar; postcode PE305AH |
| Camberwell Park Specialist Support School | CAMBERWELL PARK SCHOOL PTA (1111994) | tokens camberwell,park; postcode M409GJ |
| Flitwick Lower School | FLITWICK LOWER SCHOOL ASSOCIATION (290331) | tokens flitwick; postcode MK451LU |
| The Charter School North Dulwich | Friends of the Charter School North Dulwich (1093116) | tokens charter,north,dulwich; postcode SE249JH |
| Langtoft Primary School | FRIENDS OF LANGTOFT SCHOOL (1099046) | tokens langtoft; postcode PE69NB |
| Elham Church of England Primary School | ELHAM CEP SCHOOL PTA (1170927) | tokens elham; postcode CT46TT |
| Beaucroft Foundation School | THE FRIENDS OF BEAUCROFT SCHOOL TRUST (269510) | tokens beaucroft; postcode BH212SS |
| The Westborough School | WESTBOROUGH SCHOOL PARENT TEACHER ASSOCIATION (1206373) | tokens westborough; postcode SS09BS |
| Hindringham Church of England Primary School | FRIENDS OF HINDRINGHAM SCHOOL (1101985) | tokens hindringham; postcode NR210PL |
| Snitterfield Primary School | FRIENDS OF SNITTERFIELD SCHOOL (1049837) | tokens snitterfield; postcode CV370JL |
| Eastfield Primary School | EASTFIELD PTFA (1211951) | tokens eastfield; postcode LE48FP |
| Park Hill Junior School | PARK HILL JUNIOR SCHOOL PARENT TEACHER ASSOCIATION (1043652) | tokens park,hill; postcode CV82JJ |
| Hanson Academy | FRIENDS OF HANSON ACADEMY (1162656) | tokens hanson; postcode BD21JP |
| Juniper Hill School | JUNIPER HILL PTA (1012841) | tokens juniper,hill; postcode HP109LA |

## 25 random `sector` matches for review

| school | charity | evidence |
|---|---|---|
| St Joseph's Catholic Primary School | ST JOSEPH'S SCHOOL PARENTS TEACHERS AND FRIENDS ASSOCIATION (1056487) | tokens joseph; sector WR141, unique in WR14 |
| Hurstbourne Tarrant Church of England Primary School | FRIENDS OF HURSTBOURNE TARRANT CE PRIMARY SCHOOL ASSOCIATION (289751) | tokens hurstbourne,tarrant; sector SP110, unique in SP11 |
| Geddington Church of England Primary School | GEDDINGTON SCHOOL PARENTS' ASSOCIATION (284864) | tokens geddington; sector NN141, unique in NN14 |
| Stoke Damerel Primary Academy | STOKE DAMEREL PRIMARY SCHOOL ASSOCIATION (286538) | tokens stoke,damerel; sector PL15, unique in PL1 |
| Perry Hall Primary School | PERRY HALL PTA (1167721) | tokens perry,hall; sector WV113, unique in WV11 |
| Upland Primary School | UPLAND PRIMARY PARENTS ASSOCIATION (BEXLEYHEATH) (1111727) | tokens upland; sector DA74, unique in DA7 |
| Abbots Langley School | ABBOTS LANGLEY SCHOOL ASSOCIATION (277396) | tokens abbot,langley; sector WD50, unique in WD5 |
| All Saints' CofE Junior School | ALL SAINTS CHURCH OF ENGLAND VOLUNTARY AIDED COMMUNITY PRIMARY SCHOOL, PARENTS TEACHERS AND FRIENDS ASSOCIATION (1075595) | tokens all; sector CV345, unique in CV34 |
| Huxlow Academy | PARENTS TEACHERS & FRIENDS OF HUXLOW SCIENCE COLLEGE (1179228) | tokens huxlow; sector NN95, unique in NN9 |
| Capel Primary School | CAPEL SCHOOL PARENT TEACHER ASSOCIATION (1042135) | tokens capel; sector TN126, unique in TN12 |
| South Witham Academy | FRIENDS OF SOUTH WITHAM COMMUNITY PRIMARY SCHOOL (1094486) | tokens south,witham; sector NG335, unique in NG33 |
| Akiva School | THE AKIVA SCHOOL PARENTS-TEACHERS ASSOCIATION (287506) | tokens akiva; sector N32, unique in N3 |
| Storth CofE School | STORTH C.E. SCHOOL PTA (1107265) | tokens storth; sector LA77, unique in LA7 |
| Finmere Church of England Primary School | FRIENDS OF FINMERE SCHOOL (1042651) | tokens finmere; sector MK184, unique in MK18 |
| Talbot Primary School | TALBOT PRIMARY SCHOOL PARENT TEACHER ASSOCIATION (1093278) | tokens talbot; sector LS81, unique in LS8 |
| Long Sutton County Primary School | FRIENDS OF LONG SUTTON PRIMARY SCHOOL (1102098) | tokens long,sutton; sector PE129, unique in PE12 |
| Holymead Primary School | FRIENDS OF HOLYMEAD PRIMARY SCHOOL (1113308) | tokens holymead; sector BS44, unique in BS4 |
| Prudhoe Castle First School | PRUDHOE CASTLE FIRST SCHOOL PARENT TEACHER ASSOCIATION (1044267) | tokens prudhoe,castle; sector NE426, unique in NE42 |
| Mountjoy School | FRIENDS OF MOUNTJOY SCHOOL (1061860) | tokens mountjoy; sector DT83, unique in DT8 |
| St Paul's CofE Primary School | ST PAUL'S PARENT TEACHER ASSOCIATION (1044163) | tokens paul; sector M204, unique in M20 |
| St Anselm's Catholic Primary School | ST. ANSELM'S CATHOLIC PRIMARY SCHOOL PTA (1170894) | tokens anselm; sector SW178, unique in SW17 |
| Lambs Lane Primary School | LAMBS LANE PARENT-TEACHER ASSOCIATION (1042439) | tokens lamb,lane; sector RG71, unique in RG7 |
| Caton Primary School | CATON COMMUNITY PRIMARY SCHOOL PTA (1096315) | tokens caton; sector LA29, unique in LA2 |
| Burneston Church of England Voluntary Aided Primary School | FRIENDS OF BURNESTON SCHOOL (1051535) | tokens burneston; sector DL82, unique in DL8 |
| St Augustine's CofE Primary School | THE FRIENDS OF ST AUGUSTINE'S C.E.P. SCHOOL (1091848) | tokens augustine; sector RH177, unique in RH17 |

## 25 random `website` matches for review

| school | charity | evidence |
|---|---|---|
| St Julie's Catholic High School | ST JULIE'S PARENTS ASSOCIATION (514702) | tokens julie; website stjulies.org.uk |
| South Farnham School | SOUTH FARNHAM INFANTS PARENT ANDTEACHER ASSOCIATION (SFIPTA) (1134203) | tokens south,farnham; website south-farnham.surrey.sch.uk |
| Rossett Acre Primary School | ROSSETT ACRE PTA (1065610) | tokens rossett,acre; website rossettacreprimary.co.uk |
| Gade Valley Primary School | THE GADE VALLEY SCHOOL ASSOCIATION (1014218) | tokens gade,valley; website gadevalley.herts.sch.uk |
| Southam College | SOUTHAM COLLEGE PARENT TEACHER ASSOCIATION (1102383) | tokens southam; website southamcollege.com; phase college rules out 1 |
| Charford First School | CHARFORD FIRST SCHOOL PARENTS FRIENDS ASSOCIATION (1027644) | tokens charford; website charford.worcs.sch.uk |
| Cann Hall Primary School | THE FRIENDS OF CANN HALL SCHOOL (1132662) | tokens cann,hall; website cannhall.compassps.uk |
| Sudbourne Primary School | SUDBOURNE PARENT TEACHER ASSOCIATION (1099341) | tokens sudbourne; website sudbourne.com |
| Kennet Valley Church of England Aided Primary School | FRIENDS OF KENNET VALLEY SCHOOL (1096828) | tokens kennet,valley; website kennetvalley.wilts.sch.uk |
| Paddock School | THE FRIENDS OF PADDOCK SCHOOL (1051094) | tokens paddock; website paddock.wandsworth.sch.uk |
| Brookfield Community School | THE FRIENDS OF BROOKFIELD SCHOOL (1041541) | tokens brookfield; website brookfield.hants.sch.uk |
| Belmont Primary School | FRIENDS OF BELMONT SCHOOL (1142682) | tokens belmont; website belmont.derbyshire.sch.uk |
| Hardwick and Cambourne Community Primary School | Hardwick & Cambourne Community Primary School PTA (1122748) | tokens hardwick,cambourne; website hardwickandcambourneprimary.co.uk |
| Barnby Road Academy Primary and Nursery school | THE FRIENDS OF BARNBY ROAD SCHOOL (1092440) | tokens barnby,road; website barnbyroadprimary.com |
| St Mary's CofE Primary School | ST MARY'S N8 PSA (1178034) | tokens mary; website stmarysn8.co.uk |
| Woodfield School | FRIENDS OF WOODFIELD SCHOOL (1026216) | tokens woodfield; website woodfield.surrey.sch.uk |
| Alexander Hosea Primary School | FRIENDS OF ALEXANDER HOSEA SCHOOL (1025562) | tokens alexander,hosea; website alexanderhoseaprimary.co.uk |
| St Peter and St Paul Church Primary School | St Peter & St Paul Church Primary School PTA (1170404) | tokens peter,paul; website stpeter-stpaul.surrey.sch.uk |
| Holsworthy Church of England Primary School | HOLSWORTHY PRIMARY SCHOOL PARENT TEACHER ASSOCIATION (1050191) | tokens holsworthy; website holsworthy-primary.devon.sch.uk; phase primary rules out 1 |
| Devonport High School for Girls | DEVONPORT HIGH SCHOOL FOR GIRLS PARENT, TEACHER AND FRIENDS ASSOCIATION (1130637) | tokens devonport,girl; website dhsg.co.uk |
| St Margaret's Infant School | ST MARGARET'S INFANT SCHOOL PARENT TEACHER ASSOCIATION (1037881) | tokens margaret; website stmargaretsinf.medway.sch.uk; phase infant rules out 1 |
| Herons' Moor Academy | FRIENDS OF HERON'S MOOR SCHOOL (1106796) | tokens heron,moor; website heronsmooracademy.clf.uk |
| Moorcroft School | FRIENDS OF MOORCROFT SCHOOL (284660) | tokens moorcroft; website moorcroftschool.co.uk |
| The Vale Academy | THE VALE OF ANCHOLME TECHNOLOGY COLLEGE PARENTS' ASSOCIATION (1049513) | tokens vale; website valeacademy.org.uk |
| Watchfield Primary School | FRIENDS OF WATCHFIELD PRIMARY SCHOOL (1165973) | tokens watchfield; website watchfieldprimary.co.uk |

## 25 random `postcode-exact` matches for review

| school | charity | evidence |
|---|---|---|
| Gosforth Academy | GOSFORTH ACADEMY PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1218059) | postcode-exact NE32JH; domain gosforthacademy.org.uk (website) |
| Ladysmith Junior School | LADYSMITH SCHOOLS PARENT TEACHER ASSOCIATION (1085335) | postcode-exact EX12PS; council-unique in Devon; address-town 'Exeter' unique in Devon |
| The Hollyfield School and Sixth Form Centre | THE HOLLYFIELD SCHOOL PTA (1088409) | postcode-exact KT64TU |
| Harris Primary Academy Orpington | HARRIS PRIMARY ACADEMY ORPINGTON PTA (1188271) | postcode-exact BR54LZ; council-unique in Bromley; address-town 'Orpington' unique in Bromley |
| St Margaret's CofE Primary School, Rottingdean | FRIENDS OF ST MARGARET'S CHURCH OF ENGLAND SCHOOL (1023278) | postcode-exact BN27HB; domain stmargarets.brighton-hove.sch.uk (email) |
| Tylers Green Middle School | THE FRIENDS OF TYLERS GREEN MIDDLE SCHOOL (1066968) | postcode-exact HP108DS |
| Walton on the Naze Primary School | WALTON PRIMARY SCHOOL PTA (1132904) | postcode-exact CO148PT |
| St Oswald's Catholic Primary School, Coppull | FRIENDS OF ST OSWALD'S PTFA (1206020) | postcode-exact PR75DH |
| Bilton School | BILTON SCHOOL PTA RUGBY (1196058) | postcode-exact CV227JT; domain biltonschool.co.uk (website) |
| St Mary's Catholic Primary School | PTA OF ST MARY'S ROMAN CATHOLIC PRIMARY SCHOOL IN BROADWAY (1217150) | postcode-exact WR127DZ |
| Riverside School, Tadcaster | "FRIENDS OF RIVERSIDE SCHOOL" (1076964) | postcode-exact LS249JN |
| Saint John Fisher Catholic Voluntary Academy, Wigston, Leicestershire | ST JOHN FISHER PTFA (508144) | postcode-exact LE183QL |
| The Holbeach William Stukeley Church of England Voluntary Aided Primary School | FRIENDS OF THE WILLIAM STUKELEY CE PRIMARY SCHOOL (1096602) | postcode-exact PE127HG |
| King's Academy Gomer | FRIENDS OF GOMER JUNIOR SCHOOL (1189421) | postcode-exact PO122RP; domain kgagomer.uk (email); predecessor 'Gomer Junior School' unique in council area |
| Lift Plumberow | PLUMBEROW PRIMARY SCHOOL PTA (1114774) | postcode-exact SS55BX; predecessor 'Plumberow Primary School' unique in council area |
| St Andrew's Church of England Voluntary Aided Primary School, Hitchin | ST ANDREWS SCHOOL ASSOCIATION (801179) | postcode-exact SG49RD; domain standrews.herts.sch.uk (website) |
| Romsey Primary School & Nursery | FRIENDS OF ROMSEY PRIMARY SCHOOL (1020422) | postcode-exact SO517PH; domain romseyprimary.co.uk (website); council-unique in Hampshire; address-town 'Romsey' unique in Hampshire |
| Vernham Dean Gillum's Church of England Primary School | FRIENDS OF VERNHAM DEAN SCHOOL (1120652) | postcode-exact SP110JY |
| Bickleigh on Exe Church of England Primary School | BICKLEIGH SCHOOL ASSOCIATION (1083196) | postcode-exact EX168RE |
| St Joseph's Catholic Primary School | THE FRIENDS OF ST. JOSEPH'S SCHOOL CHALFONT ST. PETER (1069943) | postcode-exact SL98SB; domain stjosephschalfont.school (email) |
| Parsonage Farm Nursery and Infant School | FRIENDS OF PARSONAGE SCHOOL (1110755) | postcode-exact GU149TT |
| St Joseph's Roman Catholic Primary School, Darwen | ST JOSEPH'S PTFA (1218312) | postcode-exact BB32SG |
| Orion Mead Road | FRIENDS OF MEAD ROAD SCHOOL (1182880) | postcode-exact BR76AD |
| Irlam Endowed Primary School | IRLAM ENDOWED PRIMARY SCHOOL PARENT TEACHER ASSOCIATION (1104941) | postcode-exact M446EE |
| Christ Church Cep Academy, Folkestone | CHRIST CHURCH CEP SCHOOL PARENT TEACHER AND FRIENDS ASSOCIATION (290502) | postcode-exact CT201DJ |

## 25 random `domain` matches for review

| school | charity | evidence |
|---|---|---|
| St Richard's Roman Catholic Primary School Atherton | THE FRIENDS OF ST RICHARD'S RC PRIMARY SCHOOL (1104995) | domain saintrichards.wigan.sch.uk (website) |
| Widcombe Infant School | WIDCOMBE SCHOOLS PTA (1143206) | domain widcombejuniorschool.com (website); council-unique in Bath and North East Somerset; address-town 'Bath' unique in Bath and North East Somerset |
| Sutton Coldfield Grammar School for Girls | SUTTON COLDFIELD GRAMMAR SCHOOL FOR GIRLS PARENTS' ASSOCIATION (1050942) | domain suttcold.bham.sch.uk (email); council-unique in Birmingham, Coventry, Dudley, Sandwell, Solihull, Walsall, Wolverhampton; address-town 'Sutton Coldfield' unique in Birmingham |
| St Thomas' Church of England Primary School Heaton Chapel | ST THOMAS'S PAROCHIAL SCHOOL ASSOCIATION (1016973) | domain st-thomasheaton.stockport.sch.uk (website) |
| Elms Bank | PARENTS AND FRIENDS OF ELMS BANK HIGH SCHOOL (1092993) | domain elmsbank.co.uk (email); council-unique in Bury |
| Ilketshall St Lawrence School | FRIENDS OF ST LAWRENCE SCHOOL (1027075) | domain ilketshallstlawrenceprimary.co.uk (email) |
| Southwater Infant Academy | SOUTHWATER INFANT AND JUNIOR ACADEMIES PARENT TEACHER & FRIENDS ASSOCIATION (1036794) | domain southwaterjunioracademy.co.uk (website) |
| Notre Dame High School, Norwich | NOTRE DAME HIGH SCHOOL PARENTS TEACHERS & FRIENDS ASSOCIATION (1140311) | domain ndhs.org.uk (website) |
| Christ The King Catholic High School and Sixth Form Centre | CHRIST THE KING SCHOOL ASSOCIATION (1019919) | domain christtheking-school.com (email) |
| The Haven Church of England Methodist Primary School | THE HAVEN BEACONS PTFA (1098570) | domain thehaven.e-sussex.sch.uk (email) |
| The Swanage School | FRIENDS OF THE SWANAGE SCHOOL (1180403) | domain theswanageschool.co.uk (website) |
| West London Free School Primary | West London and Earls Court Free School Primaries PTA (1159396) | domain wlfs-primary.org (website) |
| St Luke's CofE Academy Endon | ST LUKE'S PARENT STAFF ASSOCIATION (1099254) | domain st-lukes-endon.staffs.sch.uk (website) |
| Sacred Heart Primary School | SACRED HEART PRIMARY SCHOOL PTFA (1203265) | domain shprimary.org.uk (email); council-unique in Newcastle upon Tyne; address-town 'Newcastle-upon-Tyne' unique in Newcastle upon Tyne |
| Chrishall Holy Trinity and St Nicholas CofE (Aided) Primary School and Pre-School | FRIENDS OF CHRISHALL SCHOOL (1069101) | domain chrishall.essex.sch.uk (email) |
| Sandwich Infant School | THE FRIENDS OF SANDWICH INFANT SCHOOL TRUST (1187600) | domain sandwich-infant.kent.sch.uk (email); council-unique in Kent; objects name 'sandwich infant school'; address-town 'Sandwich' unique in Kent |
| St Mary's Church of England Primary School, Portbury | ST MARYS CEVA PRIMARY SCHOOL FRIENDS OF THE SCHOOL (1054477) | domain stmarysprimaryportbury.co.uk (website) |
| Westwood Farm Infant School | FRIENDS OF WESTWOOD FARM SCHOOLS (1150959) | domain westwoodfarmschools.w-berks.sch.uk (website); council-unique in West Berkshire; address-town 'Reading' unique in West Berkshire |
| Benton Dene Primary School | BENTON DENE SCHOOL PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1102217) | domain bentondeneschools.org.uk (website) |
| Buckingham Primary School | BUCKINGHAM PRIMARY SCHOOL PTA (1180022) | domain buckinghamprimary.com (website); council-unique in Buckinghamshire; address-town 'Buckingham' unique in Buckinghamshire |
| Groombridge St Thomas' Church of England Primary School | FRIENDS OF GROOMBRIDGE PRIMARY SCHOOL (FGPS) (1085037) | domain groombridgest-thomas.e-sussex.sch.uk (email) |
| Maple Cross Junior Mixed Infant and Nursery School | MAPLE CROSS SCHOOL PTA (1037267) | domain maplecross.herts.sch.uk (website) |
| St Nicholas CEVC Primary School | ST NICHOLAS C OF E PRIMARY SCHOOL PTFA (STROOD) (1110554) | domain st-nicholas.medway.sch.uk (email) |
| Lazonby C of E Primary School | FRIENDS OF LAZONBY SCHOOL (1187440) | domain lazonby.cumbria.sch.uk (email); council-unique in Cumberland, Westmorland and Furness; address-town 'Penrith' unique in Westmorland and Furness |
| John Stainer Community Primary School | FRIENDS OF JOHN STAINER PTA (1104913) | domain johnstainer.lewisham.sch.uk (email); council-unique in Lewisham; address-town 'London' unique in Lewisham |

## 25 random `predecessor` matches for review

| school | charity | evidence |
|---|---|---|
| Walton Oak Primary School | SWANSMERE SCHOOL PARENT TEACHER ASSOCIATION (1032238) | predecessor 'Swansmere School' unique in council area |
| Cliff Park Ormiston Academy | FRIENDS OF CLIFF PARK HIGH SCHOOL (1053563) | predecessor 'Cliff Park High School' unique in council area |
| St James Church School | THE FRIENDS OF ARCHBISHOP CRANMER SCHOOL (1102394) | predecessor 'Archbishop Cranmer Church of England Community Primary School' unique in council area |
| Churchill Park Complex Needs School | THE FRIENDS OF ALDERMAN JACKSON SCHOOL (292208) | predecessor 'Alderman Jackson School' unique in council area |
| St Mary's Priory Junior School | OLD PRIORY JUNIOR SCHOOL PTFA (1103059) | predecessor 'Old Priory Junior School' unique in council area |
| Aylesford School Warwick | AYLESFORD SCHOOL PTA (1123244) | predecessor 'Aylesford School, A Specialist Language and Music College' unique in council area |
| The Orme Academy | WOLSTANTON HIGH SCHOOL PARENT TEACHER ASSOCIATION (1014704) | predecessor 'Wolstanton High School' unique in council area |
| Oasis Academy Long Cross | FRIENDS OF BLUEBELL VALLEY NURSERY SCHOOL (1064737) | predecessor 'Bluebell Valley Nursery School' unique in council area |
| Wyre Forest School | BLAKEBROOK SCHOOL; PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1068588) | predecessor 'Blakebrook School' unique in council area |
| Pheasey Park Farm Primary School and Early Years Centre | PHEASEY PARK FARM HOME-SCHOOL ASSOCIATION (1090169) | predecessor 'Pheasey Park Farm Primary School' unique in council area |
| Kibworth Mead Academy | KIBWORTH HIGH SCHOOL PARENT TEACHER ASSOCIATION (1049547) | predecessor 'Kibworth High School & Community Technology College' unique in council area |
| Greenfield E-ACT Primary Academy | THE FRIENDS OF GREENFIELD PRIMARY SCHOOL (1140944) | predecessor 'Greenfield Primary School' unique in council area |
| Harris City Academy Crystal Palace | HARRIS CITY ACADEMY PTFA (1117437) | predecessor 'Harris City Technology College' unique in council area |
| Freethorpe Community Primary and Nursery School | CANTLEY SCHOOL ASSOCIATION (1007107) | predecessor 'Cantley Primary School' unique in council area |
| West Lakes Academy | THE FRIENDS OF WYNDHAM SCHOOL (1096998) | predecessor 'Wyndham School' unique in council area |
| Heron Park Primary Academy | HIGHFIELD COUNTY JUNIOR SCHOOL PARENTS AND FRIENDS ASSOCIATION (1067977) | predecessor 'Highfield Junior School' unique in council area |
| Ormiston Victory Academy | FRIENDS OF COSTESSEY HIGH SCHOOL (1089836) | predecessor 'Costessey High School' unique in council area |
| Kingsbury Green Academy | THE JOHN BENTLEY SCHOOL PARENT TEACHER ASSOCIATION (1048061) | predecessor 'The John Bentley School' unique in council area |
| Heron Park Primary Academy | HAMPDEN PARK INFANT SCHOOL PARENTS AND FRIENDS ASSOCIATION (1065956) | predecessor 'Hampden Park Infant School' unique in council area |
| Windsor High School and Sixth Form | THE WINDSOR HIGH SCHOOL ASSOCIATION (1046326) | predecessor 'Windsor High School' unique in council area |
| Hill Park School | FRIENDS OF DOWNS PARK SCHOOL (1036417) | predecessor 'Downs Park School' unique in council area |
| Cranbourne | FORT HILL COMMUNITY SCHOOL PTA (1112411) | predecessor 'Fort Hill Community School' unique in council area |
| St Mary's Primary School, A Catholic Voluntary Academy | ST MARY'S CATHOLIC SCHOOL PTA, HIGH GREEN, SHEFFIELD (1113412) | predecessor 'St Mary's Catholic Primary School High Green' unique in council area |
| The Langley Heritage Primary | THE FRIENDS OF PARLAUNT PARK PRIMARY ACADEMY (1042024) | predecessor 'Parlaunt Park Primary School' unique in council area |
| Willow Park CofE Primary School | ST-MICHAEL-ON-THE MOUNT PRIMARY SCHOOL PARENT TEACHERS ASSOCIATION (1078649) | predecessor 'St Michael's on the Mount Church of England Primary School' unique in council area |

## 25 random `council-unique` matches for review

| school | charity | evidence |
|---|---|---|
| Bishop Winnington-Ingram CofE Primary School | THE PARENTS ASSOCIATION OF BISHOPS WINNINGTON-INGRAM SCHOOL (1030859) | council-unique in Hillingdon |
| Norton Canes Primary Academy | PARENTS TEACHERS AND FRIENDS ASSOCIATION OF NORTON CANES PRIMARY SCHOOL (1029807) | council-unique in Staffordshire |
| Stowupland High School | STOWUPLAND HIGH SCHOOL PARENT TEACHERS ASSOCIATION (1013053) | council-unique in Suffolk |
| Ardleigh Green Junior School | ARDLEIGH GREEN SCHOOLS PARENTS ASSOCIATION (1161575) | council-unique in Havering; address-town 'Hornchurch' unique in Havering |
| Ansford Academy | THE FRIENDS OF ANSFORD COMMUNITY SCHOOL (276752) | council-unique in Somerset; objects name 'ansford school' |
| Poltair School | POLTAIR COMMUNITY SCHOOL ASSOCIATION (1039634) | council-unique in Cornwall |
| Birdlip Primary School | BIRDLIP SCHOOL ASSOCIATION (1099884) | council-unique in Gloucestershire |
| Merton Abbey Primary School | THE FRIENDS OF MERTON ABBEY SCHOOL (297843) | council-unique in Merton |
| The Sir John Colfox Academy | SIR JOHN COLFOX SCHOOL PARENTS AND FRIENDS ASSOCIATION (270267) | council-unique in Dorset, Bournemouth, Christchurch and Poole |
| Upton Priory School | FRIENDS OF UPTON PRIORY INFANT SCHOOL (1044669) | council-unique in Cheshire East, Cheshire West and Chester |
| Thomas Walling Primary Academy | PTFA OF THOMAS WALLING SCHOOL (1109597) | council-unique in Newcastle upon Tyne |
| Elmbridge Primary School | THE FRIENDS OF ELMBRIDGE INFANTS SCHOOL (1014563) | council-unique in Gloucestershire; objects name 'elmbridge infant school' |
| Old Catton CofE VC Junior School | THE FRIENDS OF OLD CATTON CHURCH OF ENGLAND JUNIOR SCHOOL (1044052) | council-unique in Norfolk |
| Bethany Church of England Junior School | BETHANY SCHOOL ASSOCIATION (1037870) | council-unique in Dorset, Bournemouth, Christchurch and Poole |
| Rigby Hall Day Special School | FRIENDS OF RIGBY HALL SCHOOL (1042278) | council-unique in Worcestershire |
| The Folkestone School for Girls | FRIENDS OF FOLKESTONE SCHOOL FOR GIRLS (294340) | council-unique in Kent |
| Katherine Semar Infant School | FRIENDS OF KATHERINE SEMAR SCHOOLS (1015812) | council-unique in Essex |
| Saxon Mount School | FRIENDS OF SAXON MOUNT SCHOOL (1065178) | council-unique in East Sussex |
| Burton Pidsea Primary School | THE FRIENDS OF BURTON PIDSEA SCHOOL ASSOCIATION (1045734) | council-unique in East Riding of Yorkshire |
| Tanners Brook Primary School | FRIENDS OF TANNERS BROOK JUNIOR SCHOOL (1111281) | council-unique in Southampton |
| London Colney Primary & Nursery School | THE FRIENDS OF LONDON COLNEY J M I SCHOOL (1006227) | council-unique in Hertfordshire |
| St Peter's Collegiate Academy | THE FRIENDS OF ST PETERS COLLEGIATE SCHOOL ASSOCIATION (1001530) | council-unique in Wolverhampton |
| Harris Primary Academy Crystal Palace | HARRIS PRIMARY ACADEMY CRYSTAL PALACE PTA (1186191) | council-unique in Bromley |
| Lytchett Minster School | LYTCHETT MINSTER SCHOOL PARENT/TEACHER ASSOCIATION (1006454) | council-unique in Dorset, Bournemouth, Christchurch and Poole |
| Ball Green Primary Academy | BALL GREEN PRIMARY PARENT ASSOCIATION (1042897) | council-unique in Staffordshire, Stoke-on-Trent |

## 20 random `objects` matches for review

| school | charity | evidence |
|---|---|---|
| Kings Cliffe Endowed Primary School | OUNDLE & KINGS CLIFFE MIDDLE SCHOOL PFA - KINGS CLIFFE SITE (1096986) | objects name 'king cliffe middle school' |
| Sandgate School | FAMILY AND FRIENDS OF SANDGATE SCHOOL (1084131) | objects name 'sandgate school' |
| Stimpson Avenue Academy | HELPING HANDS FRIENDS OF STIMPSON AVENUE ACADEMY (1011571) | objects name 'stimpson avenue lower school' |
| Queen Elizabeth High School | QUEEN ELIZABETH HUMANITIES COLLEGE PFA (1098051) | objects name 'queen elizabeth high school' |
| Wincanton Primary School | PARENTS AND FRIENDS OF THE SCHOOL (1103324) | objects name 'wincanton primary school' |
| The Calder Learning Trust | CALDER HIGH SCHOOL PARENTS' NETWORK (1116402) | objects name 'calder high school' |
| The Topsham School | FRIENDS OF LITTLE ACORNS AT THE TOPSHAM SCHOOL (1123331) | objects name 'topsham school' |
| Abbeywood Community School | FRIENDS OF ABBEYWOOD COMMUNITY SCHOOL ENRICHMENT FUND (278226) | objects name 'abbeywood community school' |
| Hiltingbury Infant School | HILTINGBURY SCHOOLS PARENT TEACHER ASSOCIATION (HSPTA) (288984) | objects name 'hiltingbury junior school' |
| Acle Academy | ACLE ACADEMY PTA (281434) | objects name 'acle high school' |
| Rotherhithe Primary School | ROTHERHITHE PARENT TEACHER LINK (1018949) | objects name 'rotherhithe primary school' |
| Portfield School | FRIENDS OF PORTFIELD SCHOOL FOR AUTISTIC CHILDREN (262877) | objects name 'portfield school' |
| Everest Community Academy | THE JOHN HUNT OF EVEREST PARENT TEACHERS ASSOCIATION (1043212) | objects name 'everest school' |
| Rode Methodist VC First School | FRIENDS OF RODE AND NORTON SCHOOLS (1070284) | objects name 'rode methodist vc first school' |
| The Ashbeach Primary School | FRIENDS OF ASHBEACH SCHOOL IN THE COUNTY OC CAMBRIDGESHIRE (1109246) | objects name 'ashbeach school' |
| Hiltingbury Junior School | HILTINGBURY SCHOOLS PARENT TEACHER ASSOCIATION (HSPTA) (288984) | objects name 'hiltingbury junior school' |
| Reckleford Infant School and Nursery | FRIENDS OF RECKLEFORD COMMUNITY SCHOOL AND CHILDREN'S CENTRE (1119270) | objects name 'reckleford community school' |
| Flamstead Village School | FRIENDS OF FLAMSTEAD SCHOOL (1108572) | objects name 'flamstead village school' |
| Howden School | PARENT TEACHER FRIENDS ASSOCIATION OF HOWDEN SCHOOL (1000385) | objects name 'howden secondary school' |
| Fairfield School | FRIENDS OF FAIRFIELD SCHOOL (BATLEY) (1136776) | objects name 'fairfield school' |

## 16 random `address-town` matches for review

| school | charity | evidence |
|---|---|---|
| Joseph Rowntree School | FRIENDS OF JOSEPH ROWNTREE SCHOOL (1049046) | address-town 'York' unique in York |
| Cunningham Hill Junior School | CUNNINGHAM HILL SCHOOLS PTA (1194340) | address-town 'St Albans' unique in Hertfordshire |
| William Martin Church of England Junior School | FRIENDS OF WILLIAM MARTIN PTA (1205801) | address-town 'Harlow' unique in Essex |
| Garden Suburb Infant School | GARDEN SUBURB SCHOOL PARENT TEACHER TRUST (288398) | address-town 'London' unique in Barnet |
| Maidstone, St Michael's Church of England Junior School | ST MICHAEL'S MAIDSTONE PTFA (1183459) | address-town 'Maidstone' unique in Kent |
| St Elphege's RC Junior School | ST ELPHEGE'S PTFA (1173387) | address-town 'Wallington' unique in Sutton |
| St Michael's Church of England Infant School Maidstone | ST MICHAEL'S MAIDSTONE PTFA (1183459) | address-town 'Maidstone' unique in Kent |
| Mickleover Primary School | FRIENDS OF MICKLEOVER PRIMARY SCHOOL ASSOCIATION (1066771) | address-town 'Derby' unique in Derby |
| St Elphege's RC Infants' School | ST ELPHEGE'S PTFA (1173387) | address-town 'Wallington' unique in Sutton |
| Cuxton Community Infant School | CUXTON SCHOOLS PTFA (1204185) | address-town 'Rochester' unique in Medway |
| Garden Suburb Junior School | GARDEN SUBURB SCHOOL PARENT TEACHER TRUST (288398) | address-town 'London' unique in Barnet |
| Greenwood Primary and Nursery School | FRIENDS OF GREENWOOD INFANT AND NURSERY SCHOOL (F.O.G.I.N.S.) (1081801) | address-town 'Nottingham' unique in Nottinghamshire |
| Cuxton Community Junior School | CUXTON SCHOOLS PTFA (1204185) | address-town 'Rochester' unique in Medway |
| Cunningham Hill Infant School | CUNNINGHAM HILL SCHOOLS PTA (1194340) | address-town 'St Albans' unique in Hertfordshire |
| Coombe Boys' School | COOMBE BOYS' PARENT FRIENDS ASSOCIATION (1103700) | address-town 'New Malden' unique in Kingston upon Thames |
| William Martin Church of England Infant and Nursery School | FRIENDS OF WILLIAM MARTIN PTA (1205801) | address-town 'Harlow' unique in Essex |

## 25 random wider-name `postcode-exact` matches for review

| school | charity | evidence |
|---|---|---|
| The Annunciation RC Junior School | ANNUNCIATION FRIENDS (1205278) | postcode-exact HA89HQ; wider name |
| Fenstanton and Hilton Primary School | FENSTANTON & HILTON SCHOOL P.T.A. (1104778) | postcode-exact PE289JR; domain fenstantonandhiltonschool.com (website); wider name |
| Grange Valley Primary School | GRANGE VALLEY PARENT, TEACHER & FRIENDS ASSOCIATION (1217633) | postcode-exact WA110XQ; wider name |
| Mapplewells Primary and Nursery School | FRIENDS OF MAPPLEWELLS (1146291) | postcode-exact NG171HU; wider name |
| Gilbrook School | FRIENDS OF GILBROOK (514898) | postcode-exact CH498HE; domain gilbrookschool.co.uk (website); wider name |
| Bretforton Village School | BRETFORTON VILLAGE SCHOOL FRIENDS ASSOCIATION (1098434) | postcode-exact WR117JS; wider name |
| Willowbank Primary School | WILLOWBANK PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1033380) | postcode-exact EX151EZ; domain willowbank.devon.sch.uk (website); wider name |
| Bringhurst Primary School | BRINGHURST C.P. SCHOOL P.T.A. (1067566) | postcode-exact LE168RH; wider name |
| Waldegrave School | Friends of Waldegrave (297288) | postcode-exact TW25LH; domain waldegrave.richmond.sch.uk (website); wider name |
| Giles Brook Primary School | GILES BROOK FRIENDS ASSOCIATION (1101270) | postcode-exact MK43GB; wider name |
| Icknield School | FRIENDS OF ICKNIELD ASSOCIATION (900558) | postcode-exact SP116LT; wider name |
| Freeland Church of England Primary School | FREELAND SCHOOL SOCIETY (1007601) | postcode-exact OX298HX; wider name |
| Great Chart Primary School | FRIENDS ASSOCATION OF GREAT CHART PRIMARY SCHOOL (1103318) | postcode-exact TN235LB; wider name |
| Surrey Hills All Saints Primary School | FRIENDS AT SURREY HILLS SCHOOL (1137546) | postcode-exact RH43QF; domain surreyhillsprimaryschool.org.uk (website); wider name |
| Willow Dene School | FRIENDS OF WILLOW DENE (1139499) | postcode-exact SE182JD; wider name |
| Harris Academy Chobham | CHOBHAM FRIENDS (1201104) | postcode-exact E201BD; domain harrischobham.org.uk (website); wider name |
| Bleasby Church of England Primary School | BLEASBY SCHOOL FRIENDS ASSOCIATION (1132098) | postcode-exact NG147GD; domain bleasbyprimary.org.uk (email); wider name |
| Towers Junior School | FRIENDS OF TOWERS FUNDRAISING ASSOCIATION (1037283) | postcode-exact RM111PD; wider name |
| Colham Manor Primary School | Friends of Colham Manor (268197) | postcode-exact UB83PT; wider name |
| Lift Noel Park | FRIENDS OF NOEL PARK (1200578) | postcode-exact N226LH; wider name |
| Leigh Academy Dartford | DARTFORD PRIMARY ACADEMY FRIENDS ASSOCIATION (289836) | postcode-exact DA11SQ; wider name |
| Sutton Road Primary School | FRIENDS OF SUTTON ROAD (1208671) | postcode-exact NG185SF; domain suttonroad.org (email); wider name |
| Kings Hill School Primary and Nursery | KINGS HILL SCHOOL FRIENDS (1066325) | postcode-exact ME194LS; wider name |
| Penny Bridge CofE School | FRIENDS OF PENNY BRIDGE (1203053) | postcode-exact LA127RQ; wider name |
| Haberdashers' Adams | ADAMS' GRAMMAR SCHOOL SOCIETY (1167131) | postcode-exact TF107BD; domain adamsgs.uk (website); wider name |

## 25 random wider-name `domain` matches for review

| school | charity | evidence |
|---|---|---|
| Wrenthorpe Academy | WRENTHORPE PRIMARY SCHOOL FRIENDS ASSOCIATION (1043622) | domain wrenthorpeacademy.org (website); wider name |
| Ashford Oaks Community Primary School | FRIENDS OF ASHFORD OAKS (1218471) | domain ashfordoaks.kent.sch.uk (website); wider name |
| Ardleigh St Mary's Church of England Primary Academy | Friends of Ardleigh St Mary’s (1181930) | domain ardleigh.academy (email); wider name |
| St Andrew's CofE High School | FRIENDS OF ST ANDREW'S (FOSTA) (297007) | domain sta-worthing.com (website); wider name |
| St Peter's Church of England Primary School (Market Bosworth) | FRIENDS OF ST PETER'S, MARKET BOSWORTH (1129927) | domain stpeterscofemb.co.uk (website); wider name |
| Nazeing Primary School | NAZEING PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1053358) | domain nazeing.essex.sch.uk (website); wider name |
| Harewood Infant School | THE FRIENDS OF HAREWOOD (1116560) | domain harewoodjunior.co.uk (email); wider name |
| Crossdale Primary School | FRIENDS OF CROSSDALE (1018537) | domain crossdaleschool.com (website); wider name |
| Little Munden Church of England Voluntary Controlled Primary School | FRIENDS OF LITTLE MUNDEN (FOLM) (1055690) | domain littlemunden.herts.sch.uk (website); wider name |
| Morland Church of England Primary School | FRIENDS OF MORLAND (1206049) | domain morlandprimary.com (email); wider name |
| St John Fisher Primary, A Catholic Voluntary Academy | ST JOHN FISHER P.T.F.A (1150762) | domain st-johnfisher.org (email); wider name |
| Northcott School and Sixth Form College | FRIENDS OF NORTHCOTT (1050713) | domain northcottschool.org.uk (website); wider name |
| Avonmouth Church of England Primary School and Nursery | THE FRIENDS OF AVONMOUTH (1178945) | domain avonmouthp.co.uk (website); wider name |
| Tollesbury School | TOLLESBURY PARENT, TEACHER AND FRIENDS ASSOCIATION (TPTFA) (1212782) | domain tollesbury.essex.sch.uk (website); wider name |
| St Alban's Catholic Primary School | FRIENDS OF ST ALBANS ASSOCIATION (1138112) | domain stalbansschool.net (website); wider name |
| St Joseph's Catholic Primary School | ASSOCIATION OF FRIENDS OF ST JOSEPH'S, DOVERCOURT (1102272) | domain st-josephs-dovercourt.essex.sch.uk (website); wider name |
| St Matthew's CofE Primary School | FRIENDS OF ST MATTHEW'S (1179590) | domain stmatthewschadderton.co.uk (website); wider name |
| Great Denham Primary School | FRIENDS OF GREAT DENHAM (1180218) | domain greatdenhamprimary.org.uk (website); wider name |
| Shenstone School | FRIENDS OF SHENSTONE AND SVF (284108) | domain shenstone-tkat.org (email); wider name |
| Mandeville Primary School | FRIENDS OF MANDEVILLE, ST ALBANS (1108457) | domain mandeville.herts.sch.uk (website); wider name |
| St Cuthbert Mayne Catholic Primary School | FRIENDS OF ST CUTHBERT MAYNE (1140986) | domain stcuthbertmayne.co.uk (website); wider name |
| St Michael's Primary School and Nursery, Colchester | FRIENDS OF ST MICHAEL'S, COLCHESTER, ESSEX (1100336) | domain stmichaelsprimary.co.uk (email); wider name |
| St Joseph's Catholic Primary School, Otley | FRIENDS OF ST JOSEPHS OTLEY (1200981) | domain stjosephsotley.org (email); wider name |
| Gordonbrock Primary School | THE FRIENDS OF GORDONBROCK (1039517) | domain gordonbrock.lewisham.sch.uk (website); wider name |
| St Joseph's School, a Catholic Voluntary Academy | FRIENDS OF ST JOSEPH'S (1216289) | domain st-josephs.doncaster.sch.uk (email); wider name |

## Pass-1 ambiguity rejections (680)

- THE CLAYESMORE PREPARATORY SCHOOL PARENTS' ASSOCIATION TRUST FUND (268895): belongs to an independent school: Clayesmore School
- FRIENDS OF GRANVILLE SCHOOL (268910): belongs to an independent school: The Granville School
- FRIENDS OF THE OLD VICARAGE SCHOOL (270510): belongs to an independent school: The Old Vicarage School
- WHITGIFT SCHOOL PARENTS ASSOCIATION (271320): belongs to an independent school: Whitgift School
- DARRICK WOOD SCHOOL PARENTS AND STAFF ASSOCIATION (271541): charity fits several schools: Darrick Wood Infant & Nursery School; Darrick Wood Junior School; Darrick Wood School
- BACKWELL SCHOOL ASSOCIATION (272572): another school in the district also fits: Backwell School; Backwell Church of England Junior School
- CRINGLEFORD SCHOOL PARENT AND TEACHER ASSOCIATION (272879): another school in the district also fits: Cringleford CE VA Primary School; Cringleford Prep
- THE WYMONDHAM COLLEGE PARENT-STAFF ASSOCIATION (273057): charity fits several schools: Wymondham College; Wymondham College Prep School; Wymondham High Academy
- ST PETER'S SCHOOL PARENT TEACHERS ASSOCIATION MARLOW (273398): another school in the district also fits: St Peter's Catholic Primary School; Marlow Church of England Infant School
- FRIENDS OF WILLINGDON SCHOOL ASSOCIATION (273781): another school in the district also fits: Willingdon Primary School; Willingdon Community School
- STANWAY C.P. SCHOOL PTA (275342): another school in the district also fits: Stanway Primary School; The Stanway School
- BICKLEY PARK SCHOOL ASSOCIATION (275589): belongs to an independent school: Bickley Park School
- THE FRIENDS OF THE LADY ELEANOR HOLLES SCHOOL (275602): belongs to an independent school: Lady Eleanor Holles School
- ST CEDD'S SCHOOL PARENTS ASSOCIATION (276918): belongs to an independent school: St Cedd's School
- WANSTEAD HIGH SCHOOL PARENT-TEACHER ASSOCIATION (277767): another school in the district also fits: Wanstead High School; Wanstead Church School
- COLMAN SCHOOLS' PARENT-TEACHER ASSOCIATION (278445): another school in the district also fits: Colman Junior School; Colman Infant School
- FRIENDS OF MEOPHAM COMMUNITY ACADEMY (280163): another school in the district also fits: Meopham Community Academy; Meopham School
- FRIENDS OF CASTLE HILL SCHOOLS (280361): charity fits several schools: Castle Hill Infant School; Castle Hill Junior School
- FRIENDS OF GUILDFORD HIGH SCHOOL (280369): belongs to an independent school: Guildford High School
- REIGATE GRAMMAR SCHOOL PARENTS AND FRIENDS ASSOCIATION (280394): another school in the district shares the name: Reigate College; Reigate Grammar School; Reigate School

## Regenerating

Real inputs live in the main checkout (`M=/Users/jhammant/dev/personal/SchoolCatchmentArea`) and are never committed.
Back up the live output first, then write through a temp file so readers never see half a file (pta.py does the temp
file and `os.replace` itself):

```bash
cp "$M/pipeline/.cache/money/pta.json" "$M/pipeline/.cache/money/pta.json.before-wave-b"
python3 -m pipeline.money.pta                      # ~30 s; writes pta.json, pta_ambiguous.jsonl and this report
```

Adjudicator answers (method `llm`) merge only after a spot check:

```bash
python3 -m pipeline.money.pta_adjudicate import-pilot   # the pilot's full Qwen run -> pta_llm.json (no recomputation)
python3 -m pipeline.money.pta_adjudicate sample         # 50 random accepted picks -> pta_llm_review.md
# judge every row in pta_llm_review.md (right / wrong / unsure), then:
python3 -m pipeline.money.pta_adjudicate spot-check     # records spot_check {n, wrong} in pta_llm.json
python3 -m pipeline.money.pta                           # merges the answers once n >= 50 and wrong == 0
```

`--ambiguous`, `--llm` and `--crawl` default to `--out`'s directory, so a run (or a test) writing elsewhere never
touches the live cache. Older checkouts lack this: their `tests/test_pta_review.py` empties the live
`pta_ambiguous.jsonl`; rerun pta.py to restore it. `pta_crawl_review.json` is never merged.

