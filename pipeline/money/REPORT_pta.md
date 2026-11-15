# PTA matching report

Generated 2026-11-15 by `pipeline/money/pta.py` (seed 1, 71s).

- Candidate charities (main, parents' association by name): 14,123
- Wider-name candidates (Friends of X, P.T.A., Parent/Teacher, Families & Staff, Supporters of; rules f and d only): 6,629, of which 897 matched to 886 schools; 104 of the candidates are the activity-backed broad tier (a school fund or society)
- Schools matched: 10,676
- Charities matched: 11,423 (308 shared infant/junior attributions)
- By method: address-town 4, council-unique 2,098, domain 270, llm 418, objects 18, postcode 6,178, postcode-exact 1,644, predecessor 302, sector 370, website 67, website-crawl 54
- Pass-2 rules agreeing (a charity can count under several): address-town 385, council-unique 2,347, domain 939, objects 445, postcode-exact 1,644, predecessor 382
- Pass-1 ambiguity rejections: 680
- Ambiguous charities exported for adjudication: 1,447 (flagged_single_fit 442, partial_name 352, several_fit 433, single_fit_blocked 220)
- Merged from the adjudicator (llm): 418; from the website crawl: 54
- Adjudicator answers in pta_llm.json: 420, 420 accepted, 0 'shared:'; gate: open (spot check passed)
- Website crawl hits confirming an existing match (evidence gains 'website'): 1
- Annual return Part A attached: 6,580 of 11,423 matched charities
- history_status of matched charities: current 8,378, recent 485, historical 2,560
- Schools by their most recent PTA: current 8,295, recent 433, historical 1,948 (current = income for a year ending 2024 or later, recent = since 2019)

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
| Harrogate, Bilton Grange Primary School | BILTON GRANGE PRIMARY SCHOOL PARENT TEACHER ASSOCIATION (1179913) | postcode-exact HG13BA |
| Leigh Academy Bearsted | BEARSTED PRIMARY ACADEMY PTA (1193818) | postcode-exact ME145GA; domain bearstedprimaryacademy.org.uk (website) |
| Emscote Infant School | THE EMSCOTE AND ALL SAINTS PARENT TEACHER ASSOCIATION (1105107) | postcode-exact CV345NH |
| Stoke Hill Infant and Nursery School | FRIENDS OF STOKE HILL FIRST SCHOOL (1063836) | postcode-exact EX47DB; council-unique in Devon; address-town 'Exeter' unique in Devon |
| Cove Junior School | COVE JUNIOR SCHOOL ASSOCIATION (1145697) | postcode-exact GU149SA; domain covejunior.co.uk (website); council-unique in Hampshire; address-town 'Farnborough' unique in Hampshire |
| Courthouse Junior School | ALWYN AND COURTHOUSE SCHOOLS PARENT TEACHER ASSOCIATION (1014634) | postcode-exact SL65HE |
| St Mary's CofE Primary School | THE FRIENDS OF ST. MARY'S SCHOOL PTA (1049292) | postcode-exact HR14PG |
| Irlam Endowed Primary School | IRLAM ENDOWED PRIMARY SCHOOL PARENT TEACHER ASSOCIATION (1104941) | postcode-exact M446EE |
| Lincoln Monks Abbey Primary School | FRIENDS OF MONKS ABBEY PRIMARY SCHOOL (1218175) | postcode-exact LN25PF |
| Kirkburton CofE (VA) First School | FRIENDS OF KIRKBURTON FIRST SCHOOL (1158991) | postcode-exact HD80SG; domain kirkburtonfirst.co.uk (email) |
| St Andrew's Church of England Primary School, Chinnor | ST ANDREW'S SCHOOL ASSOCIATION (1184358) | postcode-exact OX394PU |
| Vale School, Worthing | Friends of Vale School (1149337) | postcode-exact BN140DB |
| Lighthouse School Leeds | LIGHTHOUSE SCHOOL PTA (1174101) | postcode-exact LS166QB |
| Benhall St Mary's Church of England Primary School | BENHALL PARENT TEACHER'S ASSOCIATION (1051663) | postcode-exact IP171HE; domain benhallschool.co.uk (email) |
| Paulton Junior School | THE PARENT-TEACHER ASSOCIATION OF PAULTON SCHOOL (310207) | postcode-exact BS397QY; domain paultonjuniorschool.co.uk (website); council-unique in Bath and North East Somerset; address-town 'Bristol' unique in Bath and North East Somerset |
| Olney Infant Academy | FRIENDS OF OLNEY INFANT ACADEMY (1076232) | postcode-exact MK465AD; domain olneyinfantacademy.co.uk (website) |
| St Mary's Church of England Primary School | FRIENDS OF ST. MARY'S C OF E (AIDED) PRIMARY SCHOOL (PULBOROUGH) (1147547) | postcode-exact RH202AN; domain st-marys-pulborough.w-sussex.sch.uk (website) |
| Tudor Grange Primary Academy Perdiswell | PERDISWELL PRIMARY SCHOOL PARENT TEACHER ASSOCIATION (1095862) | postcode-exact WR38QA; predecessor 'Perdiswell Primary School' unique in council area |
| Rowan Park School | Friends of the Rowan Schools (511943) | postcode-exact L210DB |
| Twickenham Primary Academy | Friends of Twickenham Primary Academy (1186147) | postcode-exact TW26QF |
| Hexham First School | HEXHAM EAST COUNTY FIRST SCHOOL PARENT TEACHER ASSOCIATION (1011598) | postcode-exact NE461JD; domain hexhamfirst.northumberland.sch.uk (website) |
| Morecambe Bay Academy | MORECAMBE HIGH SCHOOL PARENT TEACHER ASSOCIATION (1098407) | postcode-exact LA45BG; predecessor 'Morecambe Community High School' unique in council area |
| St Philip's CofE Primary School, Atherton | ST PHILIPS CE PTA (1208132) | postcode-exact M469FD |
| Tanners Wood Junior Mixed and Infant School | TANNERS WOOD SCHOOL ASSOCIATION (1059109) | postcode-exact WD50LG |
| Kilby St Mary's Church of England Primary School | FRIENDS OF KILBY SCHOOL (1049906) | postcode-exact LE183TD; domain kilby.leics.sch.uk (website) |

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

## 25 random `llm` matches for review

| school | charity | evidence |
|---|---|---|
| The Clarendon Academy | THE FRIENDS OF CLARENDON SCHOOL (1067275) | Charity name and objects explicitly reference Clarendon School in Trowbridge, matching the location and name of The Clarendon Academy (formerly The Clarendon College) in Trowbridge. |
| Christ Church (Erith) CofE Primary School | CHRIST CHURCH C OF E PRIMARY SCHOOL PARENTS ASSOCIATION, KENT (1011294) | The charity name matches the candidate school's name and location (Erith, Bexley) and phase (Primary). |
| St Wilfrid's Catholic Primary School | ST WILFRID'S SCHOOL PARENT TEACHER ASSOCIATION (519571) | Charity name matches the candidate school's name and location (Sheffield) fits the council area of operation. |
| The Priory Church of England School | THE FRIENDS OF THE PRIORY SCHOOL, DORKING, STAFF AND PARENTS ASSOCIATION (282794) | The charity name explicitly mentions 'The Priory School, Dorking', which matches the candidate's name and location, and the phase fits as a general association for a secondary school. |
| Springwest Academy | FELTHAM COMMUNITY SCHOOL ASSOCIATION (1001996) | The charity name 'Feltham Community School Association' matches the candidate's former name 'Feltham Community College' and the location (Feltham, Hounslow) aligns perfectly. |
| Newdigate CofE Endowed Aided Infant School | THE FRIENDS OF ST MICHAEL'S SCHOOL, MICKLEHAM (1081711) | Charity name and address match the former name and location of URN 125192 in Mickleham, Surrey. |
| Lift Bexleyheath | BEXLEYHEATH SCHOOL PARENT TEACHER ASSOCIATION (274056) | Charity name matches the candidate's former name 'Bexleyheath School' and location fits Bexleyheath in Bexley. |
| St James' Church of England Primary School | ST JAMES CE PRIMARY SCHOOL PTFA (1101797) | The charity name matches the candidate's name and the address in Hereford (HR2) aligns with the candidate's location in Hereford (HR1), whereas the other candidate is in Leominster. |
| West Bretton Junior and Infant School | FRIENDS OF BRETTON SCHOOL (FOBS) (1211223) | The charity name 'Friends of Bretton School' and its address at West Bretton Junior & Infant School match the candidate school's name and location in Wakefield. |
| Holy Trinity Church of England Primary Academy and Nursery | FRIENDS OF OSWESTRY INFANTS SCHOOL (1076615) | The charity name explicitly mentions Oswestry Infants School, which is a former name of the candidate school, and the location matches. |
| Southam Primary School | FRIENDS OF SOUTHAM PRIMARY SCHOOL (1108571) | Charity name, address, and objects explicitly match Southam Primary School (URN 143906) in Southam, Warwickshire. |
| The Frances Bardsley Academy for Girls | THE FRANCES BARDSLEY PARENT TEACHER ASSOCIATION (1023508) | Charity name matches the school's distinctive name 'Frances Bardsley' and location fits Romford/Havering. |
| Alexander McLeod Primary School | ALEX MCLEOD PTA (1158485) | Charity name 'Alex McLeod PTA' matches the distinctive name of Alexander McLeod Primary School, and the area of benefit (Greenwich) aligns with the school's location in SE2. |
| St John Fisher Catholic Primary School | THE ST JOHN FISHER PARENT TEACHER AND FRIENDS ASSOCIATION (701261) | Charity name matches the school name, and the council area (Knowsley) aligns with the school's location in Prescot. |
| The Coopers' Company and Coborn School | COOPERS COBORN PARENTS' ASSOCIATION (270893) | Charity name matches the school's distinctive name and the council area (Havering) aligns with the school's location in Upminster. |
| Greenfield Primary School | Greenfield Primary Parent Teacher Association (1103229) | Charity name matches Greenfield Primary School, and the address in Uppermill, Oldham (OL3) aligns with the candidate's location, distinct from the other Greenfield school. |
| The Trinity Catholic Academy | FRIENDS OF MOTHER TERESA PRIMARY SCHOOL (1083134) | The charity name matches the former name 'Mother Teresa Catholic Primary School' of URN 149134, and the location fits Liverpool. |
| Tadcaster Grammar School | TADCASTER GRAMMAR SCHOOL PARENTS'ASSOCIATION (1023605) | The charity name explicitly names Tadcaster Grammar School, which matches the candidate's name, location (Tadcaster, North Yorkshire), and phase (Secondary). |
| St Paul's Catholic Primary School | FRIENDS OF ST. PAUL'S RC PRIMARY SCHOOL (1104047) | Charity name and area of benefit explicitly match the candidate school's name and location in Portsmouth. |
| St. Oswald's CofE Primary School | ST OSWALD'S PRIMARY SCHOOL PARENTS AND FRIENDS GROUP (GUISELEY) (1173400) | The charity name explicitly matches St. Oswald's CofE Primary School, and the address in Guiseley (LS20) aligns with the candidate's location and phase. |
| Our Lady Star of the Sea Catholic Primary School | OUR LADY'S INFANT SCHOOL PARENTS ASSOCIATION (1042394) | The charity name 'Our Lady's Infant School' matches the candidate's former name 'Our Lady's Catholic Infant School' and the location fits the Cheshire area. |
| Newtown Primary School (High Peak Federation) | NEWTOWN SCHOOL PARENTS & FRIENDS ASSOCIATION (1065682) | Charity name and address in New Mills match the candidate school's location and name, with phase fitting a primary school. |
| Emneth Academy | FRIENDS OF EMNETH ACADEMY (1205269) | The charity name 'Friends of Emneth Academy' and its address match the candidate school's name and location exactly. |
| Pye Green Academy | PYE GREEN VALLEY PARENT TEACHER AND FRIEND ASSOCIATION (1121029) | Charity name matches the candidate's former name 'Pye Green Valley Primary School' and location matches Hednesford, Cannock. |
| Philips High School | THE FRIENDS OF PHILIPS HIGH SCHOOL (703040) | Charity name matches the candidate school name exactly, and the council area of operation (Bury) aligns with the school's location in Manchester (M45 postcode is in the Bury/Metro area). |

## 25 random `website-crawl` matches for review

| school | charity | evidence |
|---|---|---|
| St Mark's Church of England Primary School | FRIENDS OF ST MARK'S, HATCH WARREN (1188879) | https://www.stmarksprimary.net/category/fosm/ |
| Greenhill Primary School | FRIENDS OF GREENHILL SCHOOL (FROGS) (1044824) | https://www.greenhill.sheffield.sch.uk/parents-2/ |
| Hanley Swan St Gabriel's with St Mary's CofE Primary School | PARENTS AND FRIENDS OF ST GABRIELS WITH ST MARYS SCHOOL (1020134) | https://www.hanleyswanprimaryschool.co.uk/pfa/ |
| Charlton Kings Infants' School | CKIS PFA (1053722) | https://www.ckis.org.uk/pfa |
| St Boniface RC Primary School | FRIENDS OF ST BONIFACE (1093939) | https://www.stboniface.wandsworth.sch.uk/Friends-of-St-Boniface-FoSB/ |
| Totnes St John's Church of England Primary School | Totnes St John's Parents, Teachers and Friends Association (1029862) | https://www.totnesstjohnsprimary.org/ptfa |
| Colebrook Junior School | COLEBROOK FRIENDS (1069651) | https://www.colebrook-jun.swindon.sch.uk/parents/friends |
| Christ Church, Church of England Junior School, Downend | FRIENDS OF CHRIST CHURCH JUNIOR SCHOOL (1179138) | https://www.christchurchjuniors.co.uk/about-us/friends-of-ccj |
| St Francis Catholic Primary School, Goosnargh | ST FRANCIS PTA (HILL CHAPEL) (1130638) | https://www.pta-events.co.uk/stfrancisptfa/ |
| Morpeth All Saints Church of England First School | FRIENDS OF MORPETH ALL SAINTS (1046745) | https://mafs.cheviotlt.co.uk/friends-of-morpeth-all-saints-fomas/ |
| Knaresborough St John's Church of England Primary School | FRIENDS OF KNARESBOROUGH ST JOHN'S (FOKSJ) (1086071) | https://www.ksjprimaryschool.org/parents/pta-1 |
| St Peter's Eaton Square CofE Primary School | THE ST PETER'S PARENTS-TEACHERS ASSOCIATION (283529) | https://www.stpeaton.org.uk/page/?title=PTA+%26amp%3B+FUNDRAISING&pid=67 |
| Netherhall Mead Academy | FRIENDS OF NETHER HALL ASSOCIATION (514527) | https://www.netherhall-tmet.uk/our-academy/friends-of-netherhall-mead-academy-fohna/ |
| St Andrew's Church School | THE FRIENDS OF ST ANDREWS (1052031) | https://standrewsprimarybath.com/parents-carers/friends/ |
| Normandy Village School | FRIENDS OF WYKE (1161242) | https://www.normandyvillageschool.org/page/?title=Friends+of+NVS+%28PTA%29&pid=83 |
| St. George's School | FRIENDS OF ST GEORGE'S - COLCHESTER (1208195) | https://www.pta-events.com/friendsofstgeorges101/index.cfm?event=event&eventId=122165&fbclid=IwVERDUAUYugpwZG9mAWZkaWQWUOlUUyqk_H2GXf9b76VLC2VTHtmLFGV4dG4DYWVtAjExAHNydGMGYXBwX2lkCjY2Mjg1NjgzNzkAAR4i68T2ZOJG-TkoWAI8dOVQWzg2aB8V61CB40Z4C04MXZpm0zn2XIkKL3G-7Q_aem_eCw5A31M98E3xLMYlXgJpQ |
| Altrincham Grammar School for Boys | AGSB PARENTS AND FRIENDS ASSOCIATION (1186631) | https://www.agsb.co.uk/page/?title=PFA&pid=62 |
| Our Lady and St Patrick's Roman Catholic Primary School | FRIENDS OF OLSP PRIMARY SCHOOL (1171780) | https://www.pta-events.co.uk/friendsofolsp/index.cfm |
| Sutton on the Forest Church of England Voluntary Controlled Primary School | FRIENDS OF SUTTON SCHOOL (1042254) | https://suttonontheforestschool.org/friends-of-sutton-school/friends-of-sutton-school/ |
| St George's Junior School | WOODFIELD AND ST GEORGE'S PARENT, TEACHER AND FRIENDS ASSOCIATION (1201568) | https://stgeorgesjunior.org.uk/home/parents-area/useful-information/ptfa/ |
| Christ Church Primary School, Hampstead | THE FRIENDS OF CHRISTCHURCH SCHOOL (1020144) | https://christchurchschool.co.uk/parents/friends/ |
| Rathfern Primary School | FRIENDS OF RATHFERN (1086815) | https://www.rathfern.lewisham.sch.uk/Friends-of-Rathfern/ |
| St Peter and St Paul Church of England Primary School, Eye | FRIENDS OF EYE PRIMARY SCHOOL ASSOCIATION (1109125) | https://www.stpeterandstpaulschool.co.uk/page/?title=Friends+of+Eye+School&pid=62 |
| Histon and Impington Park Primary School | HI Park Primary PTFA (1096921) | https://www.parkprimary.co.uk/ptfa |
| Sacred Heart of Mary Girls' School | THE UPMINSTER CONVENT SCHOOL PARENTS, TEACHERS AND FRIENDS ASSOCIATION (312643) | https://www.sacredheartofmary.net/for-parents/ptfa/ |

## 25 random wider-name `postcode-exact` matches for review

| school | charity | evidence |
|---|---|---|
| Pashley Down Infant School | THE FRIENDS OF PASHLEY (1180438) | postcode-exact BN208NX; domain pashley.e-sussex.sch.uk (email); wider name |
| Littleport Community Primary School | Littleport Community Primary Friends Association (1124089) | postcode-exact CB61JT; wider name |
| Towers Infant School | FRIENDS OF TOWERS FUNDRAISING ASSOCIATION (1037283) | postcode-exact RM111PD; wider name |
| Marner Primary School | FRIENDS OF MARNER (1217039) | postcode-exact E33LL; domain marnerprimary.com (website); wider name |
| Howick Church Endowed Primary School | FRIENDS OF HOWICK (1194866) | postcode-exact PR10NB; wider name |
| Manor High School | FRIENDS OF MANOR HIGH (1157833) | postcode-exact LE24FU; domain manorhigh.leics.sch.uk (website); wider name |
| Bettridge School | FRIENDS OF BETTRIDGE (270831) | postcode-exact GL513AT; wider name |
| The Link School | THE LINK ASSOCIATION OF PARENTS, STAFF & FRIENDS (1103045) | postcode-exact CR04PG; wider name |
| Poverest Primary School | FRIENDS OF POVEREST (1163062) | postcode-exact BR52JD; wider name |
| St Norbert's Catholic Voluntary Academy | THE FRIENDS OF ST NORBERT'S (1096557) | postcode-exact DN174HL; domain stnorbertscrowle.co.uk (email); wider name |
| St Crispin's School | ST CRISPIN'S PARENT/TEACHER ASSOCIATION (800021) | postcode-exact RG401SS; domain crispins.co.uk (website); wider name |
| Surrey Hills All Saints Primary School | FRIENDS AT SURREY HILLS SCHOOL (1137546) | postcode-exact RH43QF; domain surreyhillsprimaryschool.org.uk (website); wider name |
| The Disraeli School | FRIENDS OF DISRAELI (1181622) | postcode-exact HP135JS; domain disraeli.bucks.sch.uk (email); wider name |
| Cold Harbour Church of England School | FRIENDS OF COLD HARBOUR (1210621) | postcode-exact MK37PD; wider name |
| Foxmoor Primary School | FRIENDS OF FOXMOOR (1112143) | postcode-exact GL54UJ; wider name |
| Brentside High School | FRIENDS @ BRENTSIDE (1184493) | postcode-exact W71JJ; wider name |
| Chirbury CofE VC Primary School & Busy Bees Nursery | Chirbury School Friends (1043533) | postcode-exact SY156BN; wider name |
| Icknield Community College | FRIENDS OF ICKNIELD (1146108) | postcode-exact OX495RB; domain icknield.oxon.sch.uk (website); wider name |
| Manor Farm Junior School | MANOR FARM COMMUNITY JUNIOR SCHOOL FUND (1071627) | postcode-exact HP157PH; domain manorfarmschool.org (website); wider name |
| Springfield House Community Special School | FRIENDS OF SPRINGFIELD HOUSE (1207281) | postcode-exact B930AJ; wider name |
| The Castle School | CASTLE SCHOOL FRIENDS (1105569) | postcode-exact BS351HT; wider name |
| Woodton Primary School | WOODTON C.P. SCHOOL P.T.A. (1078164) | postcode-exact NR352LL; wider name |
| Five Acre Wood School | FRIENDS OF FIVE ACRE WOOD AND GROW 19 (1153151) | postcode-exact ME159QF; wider name |
| Eastlands Primary School | EASTLANDS PARENTS AND STAFF ASSOCIATION (1149366) | postcode-exact CV213RY; domain eastlandsprimaryschool.co.uk (website); wider name |
| Abbots Farm Junior School | ABBOTS FARM FRIENDS (1096659) | postcode-exact CV214AP; wider name |

## 25 random wider-name `domain` matches for review

| school | charity | evidence |
|---|---|---|
| Mandeville Primary School | FRIENDS OF MANDEVILLE, ST ALBANS (1108457) | domain mandeville.herts.sch.uk (website); wider name |
| St Paul's Infant School | FRIENDS OF ST PAUL'S AND NORTH BOROUGH (1218344) | domain stpaulsmaidstone.co.uk (website); wider name |
| Shoreside Primary School | Shoreside P.T.F.A (1143040) | domain shoresideprimary.co.uk (website); wider name |
| St Michael's Primary School and Nursery, Colchester | FRIENDS OF ST MICHAEL'S, COLCHESTER, ESSEX (1100336) | domain stmichaelsprimary.co.uk (email); wider name |
| Shenstone School | FRIENDS OF SHENSTONE AND SVF (284108) | domain shenstone-tkat.org (email); wider name |
| St Denys Primary School | ST DENYS SCHOOL SUPPORTERS (1177241) | domain stdenysprimary.co.uk (website); wider name |
| Pinewood Infant and Nursery School | FRIENDS OF PINEWOOD ASSOCIATION (1051426) | domain pinewood.notts.sch.uk (email); wider name |
| The Elms Academy | FRIENDS OF THE ELMS (1220103) | domain theelmsacademy.org.uk (website); wider name |
| Morland Church of England Primary School | FRIENDS OF MORLAND (1206049) | domain morlandprimary.com (email); wider name |
| Holy Trinity CofE (C) Primary School | FRIENDS OF HOLY TRINITY (1030797) | domain holytrinity.staffs.sch.uk (email); wider name |
| Ely St John's Community Primary School | FRIENDS OF ELY ST JOHN'S (1117367) | domain elystjohns.cambs.sch.uk (website); wider name |
| Netherthong Primary School | FRIENDS OF NETHERTHONG (1152439) | domain netherthongprimary.co.uk (email); wider name |
| Simon de Senlis Primary School | FRIENDS OF SIMON DE SENLIS (1056298) | domain simondesenlis.org (website); wider name |
| St Mary's Church of England VA Primary School, Welham Green | FRIENDS OF NORTH MYMMS ST MARY'S (1087462) | domain stmarys565.herts.sch.uk (email); wider name |
| Hampton High | Friends of Hampton High (1015209) | domain hamptonhigh.org.uk (website); wider name |
| West Lancashire Community High School | PARENTS, TEACHERS AND FAMILY OF WEST LANCS COMMUNITY HIGH (1136088) | domain westlancs.lancs.sch.uk (website); wider name |
| Mora Primary School | FRIENDS OF MORA ASSOCIATION (1201034) | domain mora.brent.sch.uk (website); wider name |
| Harewood Junior School | THE FRIENDS OF HAREWOOD (1116560) | domain harewoodjunior.co.uk (email); wider name |
| Birchwood Avenue Primary School | FRIENDS OF BIRCHWOOD (1197564) | domain birchwoodavenue.herts.sch.uk (email); wider name |
| Avonmouth Church of England Primary School and Nursery | THE FRIENDS OF AVONMOUTH (1178945) | domain avonmouthp.co.uk (website); wider name |
| St Joseph's Catholic Primary School, Otley | FRIENDS OF ST JOSEPHS OTLEY (1200981) | domain stjosephsotley.org (email); wider name |
| Heltwate School | FRIENDS OF HELTWATE (1180923) | domain heltwate.co.uk (website); wider name |
| The Highway Primary School | FRIENDS OF THE HIGHWAY (802304) | domain highway.bromley.sch.uk (website); wider name |
| Hall Mead School | HALL MEAD FRIENDS' ASSOCIATION (299496) | domain hallmeadschool.com (website); wider name |
| Freethorpe Community Primary and Nursery School | FRIENDS OF FREETHORPE (1172962) | domain freethorpe.norfolk.sch.uk (website); wider name |

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

