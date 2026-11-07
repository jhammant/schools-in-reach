# PTA matching report

Generated 2026-11-07 by `pipeline/money/pta.py` (seed 1, 51s).

- Candidate charities (main, parents' association by name): 14,126
- Wider-name candidates (Friends of X, P.T.A., Parent/Teacher, Families & Staff, Supporters of; rules f and d only): 6,638, of which 899 matched to 888 schools; 105 of the candidates are the activity-backed broad tier (a school fund or society)
- Schools matched: 10,290
- Charities matched: 10,954 (308 shared infant/junior attributions)
- By method: address-town 4, council-unique 2,098, domain 270, objects 18, postcode 6,178, postcode-exact 1,647, predecessor 302, sector 370, website 67
- Pass-2 rules agreeing (a charity can count under several): address-town 385, council-unique 2,347, domain 940, objects 445, postcode-exact 1,647, predecessor 382
- Pass-1 ambiguity rejections: 680
- Ambiguous charities exported for adjudication: 1,447 (flagged_single_fit 442, partial_name 352, several_fit 433, single_fit_blocked 220)
- Merged from the adjudicator (llm): 0; from the website crawl: 0
- Adjudicator answers in pta_llm.json: 1,448, 640 accepted, 14 'shared:'; gate: no spot check recorded (pta_adjudicate.py sample, then spot-check)
- Website crawl hits confirming an existing match (evidence gains 'website'): 0
- Annual return Part A attached: 6,366 of 10,954 matched charities
- history_status of matched charities: current 8,225, recent 443, historical 2,286
- Schools by their most recent PTA: current 8,143, recent 396, historical 1,751 (current = income for a year ending 2024 or later, recent = since 2019)

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
| Seagrave Village Primary School | SEAGRAVE PTA (1175453) | postcode-exact LE127LU |
| Spalding Grammar School | PARENTS AND FRIENDS ASSOCIATION OF SPALDING GRAMMAR SCHOOL (1192524) | postcode-exact PE112XH; domain spaldinggrammar.lincs.sch.uk (website) |
| Swinderby All Saints Church of England Primary School | FRIENDS OF SWINDERBY SCHOOL (1092318) | postcode-exact LN69LU |
| The Snaith School | The Snaith School Association (1064026) | postcode-exact DN149LB; domain thesnaithschool.org.uk (email) |
| St Mary's Church of England Primary School | FRIENDS OF ST. MARY'S C OF E (AIDED) PRIMARY SCHOOL (PULBOROUGH) (1147547) | postcode-exact RH202AN; domain st-marys-pulborough.w-sussex.sch.uk (website) |
| Harford Manor School, Norwich | FRIENDS OF HARFORD MANOR SCHOOL (1013842) | postcode-exact NR22LN; domain harfordmanor.norfolk.sch.uk (website) |
| Markyate Village School and Nursery | FRIENDS OF MARKYATE SCHOOL (1048983) | postcode-exact AL38PT; domain markyate.herts.sch.uk (email) |
| Thorneyholme Roman Catholic Primary School, Dunsop Bridge | FRIENDS OF THORNEYHOLME SCHOOL (1105010) | postcode-exact BB73BG |
| Gosforth Academy | GOSFORTH ACADEMY PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1218059) | postcode-exact NE32JH; domain gosforthacademy.org.uk (website) |
| Christ's Church of England Comprehensive Secondary School | CHRIST'S SCHOOL PTA (1158685) | postcode-exact TW106HW; domain christs.richmond.sch.uk (website) |
| St Michael's Church of England Infant School Maidstone | ST MICHAEL'S MAIDSTONE PTFA (1183459) | postcode-exact ME168ER; address-town 'Maidstone' unique in Kent |
| St John the Baptist Catholic Primary School, Andover | FRIENDS OF ST JOHN THE BAPTIST SCHOOL (1149558) | postcode-exact SP103PF; domain sjbschool.co.uk (website) |
| Portman Early Childhood Centre | PORTMAN NURSERY PARENTS AND TEACHERS ASSOCIATION (1174205) | postcode-exact NW88DE; domain portmancentre.co.uk (website) |
| Thornton Cleveleys Baines Endowed Voluntary Controlled Primary School | THE FRIENDS OF BAINES' ENDOWED SCHOOL (THORNTON) (1050798) | postcode-exact FY55HY |
| Springfield School | SPRINGFIELD SCHOOL, WITNEY, PARENT TEACHERS ASSOCIATION (309567) | postcode-exact OX281AR; domain springfield.oxon.sch.uk (website); objects name 'springfield school' |
| Rokesly Junior School | ROKESLY PSA (1177109) | postcode-exact N88NH; council-unique in Haringey; address-town 'London' unique in Haringey |
| Olney Middle School | FRIENDS OF OLNEY MIDDLE SCHOOL (1146347) | postcode-exact MK465DZ; domain olneymiddle.milton-keynes.sch.uk (website) |
| Chalkwell Hall Junior School | CHALKWELL HALL INFANT JUNIOR PTA (1094927) | postcode-exact SS93NL; council-unique in Essex, Southend-on-Sea; address-town 'Leigh-on-Sea' unique in Southend-on-Sea |
| St John the Evangelist RC Primary School, Bromley Cross, Bolton | THE FRIENDS OF ST JOHN'S SCHOOL (510093) | postcode-exact BL79HT; domain st-johns-bromley-cross.bolton.sch.uk (email) |
| Bournes Green Junior School | The Parents Association of Bournes Green Schools (1184619) | postcode-exact SS13PS; address-town 'Southend-on-Sea' unique in Southend-on-Sea |
| The King's School, Grantham | KING'S SCHOOL PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1011173) | postcode-exact NG316RP; domain kings.lincs.sch.uk (website) |
| Birchwood Grove Community Primary School, Burgess Hill | BIRCHWOOD GROVE SCHOOL PTA (1098076) | postcode-exact RH150DP |
| Barrow Hall Orchard Church of England Primary School | HALL ORCHARD CE PRIMARY SCHOOL PTFA (1206987) | postcode-exact LE128HP; domain hall-orchard.leics.sch.uk (email) |
| St Bartholomew's Church of England Voluntary Aided Primary School, Wigginton | WIGGINTON SCHOOL ASSOCIATION (1059065) | postcode-exact HP236EP; domain stbarts.herts.sch.uk (website) |
| Everton Heath Primary School | EVERTON LOWER SCHOOL PARENT TEACHER ASSOCIATION (1049857) | postcode-exact SG192LE |

## 25 random `domain` matches for review

| school | charity | evidence |
|---|---|---|
| Holy Trinity CofE Primary School, Lower Beeding | HOLY TRINITY C.E.P. SCHOOL PARENT TEACHER ASSOCIATON (1098901) | domain htlb.school (website) |
| St John's RC Primary School, a Voluntary Academy | ST JOHN'S RC PRIMARY SCHOOL PTA CHORLTON (1166215) | domain stjohnsrc.net (website) |
| Central Primary School | PARENT STAFF ASSOCIATION (273238) | domain central.herts.sch.uk (website) |
| The Haven Church of England Methodist Primary School | THE HAVEN BEACONS PTFA (1098570) | domain thehaven.e-sussex.sch.uk (email) |
| William de Ferrers School | FRIENDS OF WILLIAM DE FERRERS SCHOOL (286706) | domain wdf.school (email); council-unique in Essex; address-town 'Chelmsford' unique in Essex |
| Lift Hamford | All Hands on Deck Hamford PTA (1065065) | domain lifthamford.org (email) |
| High Lawn Primary School | HIGH LAWN CP SCHOOL PTA (1152715) | domain high-lawn.bolton.sch.uk (email) |
| Gracewood Academy | MOUNT GRACE SCHOOL PARENT TEACHER AND FRIENDS ASSOCIATION (1120903) | domain gracewood.futureacademies.org (website); predecessor 'Mount Grace School' unique in council area |
| St Nicholas CEVC Primary School | ST NICHOLAS C OF E PRIMARY SCHOOL PTFA (STROOD) (1110554) | domain st-nicholas.medway.sch.uk (email) |
| St Charles' Catholic Voluntary Academy | ST CHARLES HADFIELD PARENT TEACHERS ASSOCIATION (1109416) | domain st-charles.derbyshire.sch.uk (email) |
| James Wolfe Primary School and Centre for the Deaf | FRIENDS OF JAMES WOLFE SCHOOL (1085963) | domain jameswolfe.greenwich.sch.uk (website); predecessor 'James Wolfe Junior School' unique in council area |
| Stamford St Gilberts Church of England Primary School | ST GILBERT'S PTA (1128751) | domain stgilberts.co.uk (website) |
| Harris Primary Academy Beckenham Green | BROMLEY ROAD PARENT TEACHER ASSOCIATION (1023475) | domain harrisbeckenhamgreen.org.uk (email); predecessor 'Bromley Road Primary School' unique in council area |
| Wheatley Church of England Primary School | WHEATLEY PRIMARY SCHOOL PTA (1177673) | domain wheatley.oxon.sch.uk (website) |
| Benton Dene Primary School | BENTON DENE SCHOOL PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1102217) | domain bentondeneschools.org.uk (website) |
| Whitstone Primary School | WHITSTONE CP SCHOOL PARENT TEACHERS AND FRIENDS ASSOCIATION (1039075) | domain whitstone.cornwall.sch.uk (email) |
| Whitefield School | THE FRIENDS OF WHITEFIELD SCHOOLS (267817) | domain whitefield.org.uk (email); council-unique in Waltham Forest; objects name 'whitefield school' |
| St Patrick's Catholic Primary Academy | PARENTS AND FRIENDS ASSOCIATION OF ST PATRICK'S PRIMARY SCHOOL BIRSTALL (1032453) | domain stpatricksbirstall.co.uk (website) |
| St Richard's Roman Catholic Primary School Atherton | THE FRIENDS OF ST RICHARD'S RC PRIMARY SCHOOL (1104995) | domain saintrichards.wigan.sch.uk (website) |
| Holy Cross Catholic Primary School | HOLY CROSS ROMAN CATHOLIC SCHOOL PTFA (1105108) | domain holycross.plymouth.sch.uk (email); address-town 'Plymouth' unique in Plymouth |
| St Anne's Catholic High School for Girls | FRIENDS OF ST. ANNE'S SCHOOL ENFIELD (FOSA) (1164707) | domain st-annes.enfield.sch.uk (website) |
| Brant Broughton Church of England and Methodist Primary School | BRANT BROUGHTON PTA (1087316) | domain brant-broughton.lincs.sch.uk (website) |
| St Paul's Catholic Primary School, a Voluntary Academy | FRIENDS OF ST PAUL'S SCHOOL, ALWOODLEY (1102434) | domain stpaulscps.com (website); objects name 'st paul school' |
| Brixham Church of England Primary School | Brixham C of E PTFA (1076732) | domain brixhamcofe.org (email) |
| Kelvedon Hatch Community Primary School | KELVEDON HATCH COMMUNITY PRIMARY SCHOOL PTA (1108061) | domain kelvedonhatch.essex.sch.uk (email); council-unique in Essex |

## 25 random `predecessor` matches for review

| school | charity | evidence |
|---|---|---|
| Surrey Hills All Saints Primary School | THE FRIENDS OF ABINGER COMMON SCHOOL (1047205) | predecessor 'Abinger Common First School' unique in council area |
| Three Peaks Primary Academy | THE DALES INFANT SCHOOL PARENT TEACHER AND FRIENDS ASSOCIATION (1080852) | predecessor 'The Dales Infants' School' unique in council area |
| Wodensborough Ormiston Academy | WODENSBOROUGH PARENT TEACHER ASSOCIATION (1033010) | predecessor 'Wodensborough Community Technology College' unique in council area |
| Saint Nathaniel's Academy | JOHN BASKEYFIELD VC C OF E C PRIMARY SCHOOL PTA (1116303) | predecessor 'John Baskeyfield VC CofE Primary School' unique in council area |
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

## 25 random `council-unique` matches for review

| school | charity | evidence |
|---|---|---|
| Cheltenham Bournside School and Sixth Form Centre | CHELTENHAM BOURNSIDE SCHOOL AND SIXTH FORM CENTRE PARENTS ASSOCIATION (1068981) | council-unique in Gloucestershire |
| Clapham and Patching CofE Primary School | CLAPHAM & PATCHING SCHOOL PTA (1117378) | council-unique in West Sussex |
| Bishop Winnington-Ingram CofE Primary School | THE PARENTS ASSOCIATION OF BISHOPS WINNINGTON-INGRAM SCHOOL (1030859) | council-unique in Hillingdon |
| Trentham Academy | TRENTHAM HIGH SCHOOL PARENT STAFF ASSOCIATION (1032343) | council-unique in Staffordshire, Stoke-on-Trent |
| Jarvis Brook Primary School | JARVIS BROOK SCHOOL ASSOCIATION (1014965) | council-unique in East Sussex |
| Leedstown Community Primary School | FRIENDS OF LEEDSTOWN SCHOOL (1016239) | council-unique in Cornwall |
| Ansford Academy | THE FRIENDS OF ANSFORD COMMUNITY SCHOOL (276752) | council-unique in Somerset; objects name 'ansford school' |
| Mary Hare School | MARY HARE GRAMMAR SCHOOL PARENT TEACHER ASSOCIATION (1041326) | council-unique in West Berkshire; address-town 'Newbury' unique in West Berkshire |
| Birdlip Primary School | BIRDLIP SCHOOL ASSOCIATION (1099884) | council-unique in Gloucestershire |
| Merton Abbey Primary School | THE FRIENDS OF MERTON ABBEY SCHOOL (297843) | council-unique in Merton |
| The Sir John Colfox Academy | SIR JOHN COLFOX SCHOOL PARENTS AND FRIENDS ASSOCIATION (270267) | council-unique in Dorset, Bournemouth, Christchurch and Poole |
| Upton Priory School | FRIENDS OF UPTON PRIORY INFANT SCHOOL (1044669) | council-unique in Cheshire East, Cheshire West and Chester |
| Wrenn School | WRENN SCHOOL ASSOCIATION (1115401) | council-unique in North Northamptonshire, West Northamptonshire |
| Elmbridge Primary School | THE FRIENDS OF ELMBRIDGE INFANTS SCHOOL (1014563) | council-unique in Gloucestershire; objects name 'elmbridge infant school' |
| Four Lanes Community Junior School | FRIENDS OF FOUR LANES SCHOOLS (1045099) | council-unique in Hampshire |
| Corpus Christi Catholic Primary School | CORPUS CHRISTI SCHOOL PARENTS AND FRIENDS ASSOCIATION (1039721) | council-unique in North Somerset |
| Cummersdale School | FRIENDS OF CUMMERSDALE SCHOOL (1043328) | council-unique in Cumberland, Westmorland and Furness |
| Windmill Primary School | RAUNDS WINDMILL SCHOOL ASSOCIATION (295511) | council-unique in North Northamptonshire, West Northamptonshire |
| Paulet High School | PAULET HIGH SCHOOL PARENT TEACHERS ASSOCIATION (1017647) | council-unique in Staffordshire |
| Farsley Farfield Primary School | FARSLEY FARFIELD PRIMARY SCHOOL PARENT AND TEACHERS ASSOCIATION (1071560) | council-unique in Bradford, Calderdale, Kirklees, Leeds, Wakefield |
| Scamblesby Church of England Primary School | PARENT TEACHER AND FRIENDS ASSOCIATION OF SCAMBLESBY C OF E PRIMARY SCHOOL (1047890) | council-unique in Lincolnshire |
| Tanners Brook Primary School | FRIENDS OF TANNERS BROOK JUNIOR SCHOOL (1111281) | council-unique in Southampton |
| Wix and Wrabness Primary School | THE FRIENDS OF WIX AND WRABNESS PRIMARY SCHOOL (1009828) | council-unique in Essex |
| Hob Green Primary School | HOB GREEN PARENT TEACHER ASSOCIATION (1003219) | council-unique in Dudley |
| Queen Mary's High School | QUEEN MARY'S HIGH SCHOOL PARENTS AND FRIENDS ASSOCIATION (1010084) | council-unique in Birmingham, Coventry, Dudley, Sandwell, Solihull, Walsall, Wolverhampton |

## 18 random `objects` matches for review

| school | charity | evidence |
|---|---|---|
| Stimpson Avenue Academy | HELPING HANDS FRIENDS OF STIMPSON AVENUE ACADEMY (1011571) | objects name 'stimpson avenue lower school' |
| Rotherhithe Primary School | ROTHERHITHE PARENT TEACHER LINK (1018949) | objects name 'rotherhithe primary school' |
| Wincanton Primary School | PARENTS AND FRIENDS OF THE SCHOOL (1103324) | objects name 'wincanton primary school' |
| Rode Methodist VC First School | FRIENDS OF RODE AND NORTON SCHOOLS (1070284) | objects name 'rode methodist vc first school' |
| Acle Academy | ACLE ACADEMY PTA (281434) | objects name 'acle high school' |
| Kings Cliffe Endowed Primary School | OUNDLE & KINGS CLIFFE MIDDLE SCHOOL PFA - KINGS CLIFFE SITE (1096986) | objects name 'king cliffe middle school' |
| Sandgate School | FAMILY AND FRIENDS OF SANDGATE SCHOOL (1084131) | objects name 'sandgate school' |
| The Calder Learning Trust | CALDER HIGH SCHOOL PARENTS' NETWORK (1116402) | objects name 'calder high school' |
| The Topsham School | FRIENDS OF LITTLE ACORNS AT THE TOPSHAM SCHOOL (1123331) | objects name 'topsham school' |
| Abbeywood Community School | FRIENDS OF ABBEYWOOD COMMUNITY SCHOOL ENRICHMENT FUND (278226) | objects name 'abbeywood community school' |
| Howden School | PARENT TEACHER FRIENDS ASSOCIATION OF HOWDEN SCHOOL (1000385) | objects name 'howden secondary school' |
| The Ashbeach Primary School | FRIENDS OF ASHBEACH SCHOOL IN THE COUNTY OC CAMBRIDGESHIRE (1109246) | objects name 'ashbeach school' |
| Portfield School | FRIENDS OF PORTFIELD SCHOOL FOR AUTISTIC CHILDREN (262877) | objects name 'portfield school' |
| Everest Community Academy | THE JOHN HUNT OF EVEREST PARENT TEACHERS ASSOCIATION (1043212) | objects name 'everest school' |
| Flamstead Village School | FRIENDS OF FLAMSTEAD SCHOOL (1108572) | objects name 'flamstead village school' |
| Reckleford Infant School and Nursery | FRIENDS OF RECKLEFORD COMMUNITY SCHOOL AND CHILDREN'S CENTRE (1119270) | objects name 'reckleford community school' |
| Fairfield School | FRIENDS OF FAIRFIELD SCHOOL (BATLEY) (1136776) | objects name 'fairfield school' |
| Queen Elizabeth High School | QUEEN ELIZABETH HUMANITIES COLLEGE PFA (1098051) | objects name 'queen elizabeth high school' |

## 4 random `address-town` matches for review

| school | charity | evidence |
|---|---|---|
| Coombe Boys' School | COOMBE BOYS' PARENT FRIENDS ASSOCIATION (1103700) | address-town 'New Malden' unique in Kingston upon Thames |
| Joseph Rowntree School | FRIENDS OF JOSEPH ROWNTREE SCHOOL (1049046) | address-town 'York' unique in York |
| Greenwood Primary and Nursery School | FRIENDS OF GREENWOOD INFANT AND NURSERY SCHOOL (F.O.G.I.N.S.) (1081801) | address-town 'Nottingham' unique in Nottinghamshire |
| Mickleover Primary School | FRIENDS OF MICKLEOVER PRIMARY SCHOOL ASSOCIATION (1066771) | address-town 'Derby' unique in Derby |

## 25 random wider-name `postcode-exact` matches for review

| school | charity | evidence |
|---|---|---|
| Georgian Gardens Community Primary School | GEORGIAN GARDENS C.P. SCHOOL P.T.A. (1106660) | postcode-exact BN163JJ; wider name |
| Rudyard Kipling Primary School & Nursery | RUDYARD KIPLING PARENT/TEACHER/FRIENDS ASSOCIATION (1026027) | postcode-exact BN26RH; wider name |
| Lanterns Nursery School and Extended Services | FRIENDS OF LANTERNS (269085) | postcode-exact SO226AJ; wider name |
| Orford Church of England Primary School and Nursery | ORFORD SCHOOL LEAGUE OF FRIENDS (1218633) | postcode-exact IP122LU; wider name |
| Edmund Waller Primary School | EDMUND WALLER P.T.A (1031811) | postcode-exact SE145LY; domain edmundwaller.lewisham.sch.uk (website); wider name |
| Ermington Primary School | ERMINGTON SCHOOL FUNDRAISING ASSOCIATION (1117752) | postcode-exact PL219NH; wider name |
| Mossgate Primary School | MOSSGATE FRIENDS, FAMILIES AND STAFF (1215978) | postcode-exact LA32EE; domain mossgate.lancs.sch.uk (website); wider name |
| Applegarth Primary School | FRIENDS OF APPLEGARTH (1153754) | postcode-exact DL78QF; domain applegarth.n-yorks.sch.uk (email); wider name |
| Watling Park School | FRIENDS OF WATLING  PARK (1211577) | postcode-exact HA89YA; domain watlingparkschool.org.uk (website); wider name |
| Lowtown Primary School | PUDSEY LOWTOWN WISEOWL PARENT, TEACHER AND FRIENDS ASSOCIATION (1111080) | postcode-exact LS289BB; domain pudseylowtown.org.uk (website); wider name |
| Floreat Montague Park Primary School and Nursery | FRIENDS OF FLOREAT MONTAGUE PARK (1171956) | postcode-exact RG401BG; wider name |
| Manorbrook Primary School | FRIENDS OF MANORBROOK (1052125) | postcode-exact BS351JW; domain manorbrook.org.uk (website); wider name |
| Somerdale Educate Together Primary Academy | FRIENDS OF SOMERDALE EDUCATE TOGETHER (1197992) | postcode-exact BS312FF; wider name |
| Mulberry West St Leonards Primary | FRIENDS OF WEST ST. LEONARDS (1213539) | postcode-exact TN388BX; wider name |
| Yattendon School | FRIENDS OF YATTENDON (1159383) | postcode-exact RH67BZ; domain yattendon.org (website); wider name |
| John Jamieson School | JOHN JAMIESON AND HOSPITAL SCHOOLS' FRIENDS GROUP (1119800) | postcode-exact LS82PW; domain eastsilc.org (email); wider name |
| Burnt Ash Primary School | BURNT ASH PRIMARY SCHOOL P.T.A (1052481) | postcode-exact BR14QX; domain burntash.bromley.sch.uk (website); wider name |
| Lime Tree Primary School and Nursery | FRIENDS OF LIME TREE (1163208) | postcode-exact RH13LH; wider name |
| Barton Clough Primary School | FRIENDS OF BARTON CLOUGH (1203390) | postcode-exact M329TG; wider name |
| Threshfield Primary School | THRESHFIELD SCHOOL FUND (1048079) | postcode-exact BD235NP; wider name |
| Sandfield Primary School | FRIENDS OF SANDFIELD (1106505) | postcode-exact GU14DT; domain sandfield.surrey.sch.uk (website); wider name |
| Hospital and Outreach Education | HOSPITAL AND OUTREACH EDUCATION PARENT, TEACHER AND FRIENDS ASSOCIATION (1210331) | postcode-exact NN48EN; wider name |
| Oaklands School | FRIENDS OF OAKLANDS (1183493) | postcode-exact ME50QS; wider name |
| Rogate CofE Primary School | ROGATE SCHOOL FAMILY AND FRIENDS (1089746) | postcode-exact GU315HH; wider name |
| Barrow Hall Community Primary School | FRIENDS OF BARROW HALL (1207243) | postcode-exact WA53TX; domain barrowhall.co.uk (website); wider name |

## 25 random wider-name `domain` matches for review

| school | charity | evidence |
|---|---|---|
| Netherthong Primary School | FRIENDS OF NETHERTHONG (1152439) | domain netherthongprimary.co.uk (email); wider name |
| Fordwater School, Chichester | FORDWATER PARENTS AND TEACHERS ASSOCIATION (801784) | domain fordwatersch.co.uk (website); wider name |
| All Saints CofE Academy Denstone | FRIENDS OF ALL SAINTS, DENSTONE (1102403) | domain allsaints-denstone.staffs.sch.uk (website); wider name |
| Doubletrees School | FRIENDS OF DOUBLETREES (1027045) | domain doubletrees.org.uk (website); wider name |
| Simon de Senlis Primary School | FRIENDS OF SIMON DE SENLIS (1056298) | domain simondesenlis.org (website); wider name |
| Dovedale Community Primary School | FRIENDS OF DOVEDALE (516176) | domain dovedaleprimary.co.uk (website); wider name |
| Benhurst Primary School | FRIENDS OF BENHURST ASSOCIATION (1106626) | domain benhurst.havering.sch.uk (email); wider name |
| St James's Church of England High School | ST JAMES C OF E SCHOOL APPEALS ASSOCIATION (1003076) | domain st-james.bolton.sch.uk (email); wider name |
| Kingfisher Community Primary School | FRIENDS OF KINGFISHER (1003585) | domain kingfisher-gst.org (website); wider name |
| Middleton Primary School | FRIENDS OF MIDDLETON (1105240) | domain middletonschool.org (website); wider name |
| Ashford Oaks Community Primary School | FRIENDS OF ASHFORD OAKS (1218471) | domain ashfordoaks.kent.sch.uk (website); wider name |
| St Denys Primary School | ST DENYS SCHOOL SUPPORTERS (1177241) | domain stdenysprimary.co.uk (website); wider name |
| St Bede's Catholic Primary School | FRIENDS OF ST BEDE'S COMMUNITY GROUP (1149272) | domain stbedescatholicprimary.co.uk (website); wider name |
| Morland Church of England Primary School | FRIENDS OF MORLAND (1206049) | domain morlandprimary.com (email); wider name |
| Weston-on-Trent CofE (VA) Primary School | WESTON ON TRENT PARENTS, STAFF AND FRIENDS ASSOCIATION (1072087) | domain westoncofe.derbyshire.sch.uk (email); wider name |
| Northbourne Church of England Primary School | FRIENDS OF NORTHBOURNE (1028822) | domain northbourne-cep.kent.sch.uk (website); wider name |
| Woolgrove School, Special Needs Academy | FOW FRIENDS OF WOOLGROVE (1198782) | domain woolgrove.herts.sch.uk (website); wider name |
| St Andrew's CofE High School | FRIENDS OF ST ANDREW'S (FOSTA) (297007) | domain sta-worthing.com (website); wider name |
| Norton St Nicholas CofE (VA) Primary School | ST NICHOLAS ASSOCIATION OF PARENTS AND STAFF. (1060846) | domain nortonstnicholas.co.uk (website); wider name |
| St Agnes' Catholic Primary School | FRIENDS OF ST AGNES (F.O.S.A) (1171612) | domain stagnesnw2.co.uk (website); wider name |
| Roseberry Academy | ROSEBERRY ACADEMY FRIENDS AND TEACHERS (1040735) | domain roseberryacademy.org (email); wider name |
| Ivy Lane Primary School | FRIENDS OF IVY LANE (FOILS) (1187727) | domain ivylane.wilts.sch.uk (website); wider name |
| St Teresa's Catholic Primary School, Colchester | FRIENDS OF ST TERESA’S, COLCHESTER (1206040) | domain st-teresas.essex.sch.uk (email); wider name |
| St Michael's Church of England Primary School, Alkrington | ST MICHAEL'S ALKRINGTON PARENT, TEACHERS AND FRIENDS ASSOCIATION (1130140) | domain stmichaelscemidd.rochdale.sch.uk (website); wider name |
| Pinewood Infant and Nursery School | FRIENDS OF PINEWOOD ASSOCIATION (1051426) | domain pinewood.notts.sch.uk (email); wider name |

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
Back up the live output first (`-n`: the first, pre-Wave-B backup is never overwritten), then write through a temp
file so readers never see half a file (pta.py does the temp file and `os.replace` itself):

```bash
cp -n "$M/pipeline/.cache/money/pta.json" "$M/pipeline/.cache/money/pta.json.before-wave-b"
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

