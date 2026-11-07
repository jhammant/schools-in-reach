# PTA matching report

Generated 2026-11-07 by `pipeline/money/pta.py` (seed 1, 26s).

- Candidate charities (main, parents' association by name): 14,126
- Schools matched: 9,468
- Charities matched: 10,021 (238 shared infant/junior attributions)
- By method: address-town 16, council-unique 2,177, domain 128, objects 20, postcode 6,178, postcode-exact 764, predecessor 301, sector 370, website 67
- Pass-2 rules agreeing (a charity can count under several): address-town 363, council-unique 2,322, domain 441, objects 445, postcode-exact 764, predecessor 381
- Pass-1 ambiguity rejections: 680
- Ambiguous charities exported for adjudication: 1,448 (flagged_single_fit 442, partial_name 337, several_fit 448, single_fit_blocked 221)
- Merged from the adjudicator (llm): 0; from the website crawl: 0
- Annual return Part A attached: 5,790 of 10,021 matched charities

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
| Broughton-in-Amounderness Church of England Primary School | FRIENDS OF BROUGHTON PRIMARY SCHOOL (1218944) | postcode-exact PR35JB; domain broughtonprimary.co.uk (email) |
| Egglescliffe Church of England Primary School | FRIENDS OF EGGLESCLIFFE CE PRIMARY SCHOOL (1085585) | postcode-exact TS169BT; address-town 'Stockton-on-Tees' unique in Stockton-on-Tees |
| St John the Evangelist CofE Primary School Macclesfield | ST JOHN THE EVANGELIST PARENT TEACHER ASSOCIATION (1089197) | postcode-exact SK118QN |
| The Good Shepherd Catholic Primary, Arnold | THE GOOD SHEPHERD PRIMARY CATHOLIC ACADEMY PARENT TEACHER ASSOCIATION (1191867) | postcode-exact NG54LT; domain goodshepherd.notts.sch.uk (email) |
| St Margaret's CofE Primary School, Rottingdean | FRIENDS OF ST MARGARET'S CHURCH OF ENGLAND SCHOOL (1023278) | postcode-exact BN27HB; domain stmargarets.brighton-hove.sch.uk (email) |
| Tylers Green Middle School | THE FRIENDS OF TYLERS GREEN MIDDLE SCHOOL (1066968) | postcode-exact HP108DS |
| Fittleworth CofE Village School | FITTLEWORTH PTA (1136404) | postcode-exact RH201JB |
| Shipston-on-Stour Primary School | FRIENDS OF SHIPSTON PRIMARY (1208478) | postcode-exact CV364BT |
| All Saints Church of England Primary School, Newmarket | FRIENDS OF ALL SAINTS' SCHOOL PTA (1196436) | postcode-exact CB88JE; domain allsaints.suffolk.sch.uk (website) |
| Elm Grove Primary School, Worthing | ELM GROVE PRIMARY PSA (1217314) | postcode-exact BN115LQ; domain elmgrove.org.uk (website) |
| Riverside School, Tadcaster | "FRIENDS OF RIVERSIDE SCHOOL" (1076964) | postcode-exact LS249JN |
| Saint John Fisher Catholic Voluntary Academy, Wigston, Leicestershire | ST JOHN FISHER PTFA (508144) | postcode-exact LE183QL |
| Holy Cross Catholic Primary School, Harlow | HOLY CROSS SCHOOL PTA (1097300) | postcode-exact CM186JJ |
| Buxton Junior School | BUXTON JUNIOR SCHOOL PTFA (1189532) | postcode-exact SK179DR; council-unique in Derbyshire; address-town 'Buxton' unique in Derbyshire |
| Rawtenstall St Paul's Church of England Primary School | ST. PAUL'S SCHOOL PTA (1114103) | postcode-exact BB48HW; domain stpaulsrawtenstall.co.uk (website) |
| St Andrew's Church of England Voluntary Aided Primary School, Hitchin | ST ANDREWS SCHOOL ASSOCIATION (801179) | postcode-exact SG49RD; domain standrews.herts.sch.uk (website) |
| Romsey Primary School & Nursery | FRIENDS OF ROMSEY PRIMARY SCHOOL (1020422) | postcode-exact SO517PH; domain romseyprimary.co.uk (website); council-unique in Hampshire; address-town 'Romsey' unique in Hampshire |
| Cheadle Primary School | CHEADLE PRIMARY SCHOOL PARENTS TEACHER AND FRIEND ASSOCIATION (1121656) | postcode-exact ST101EN; council-unique in Staffordshire; address-town 'Stoke-on-Trent' unique in Staffordshire |
| Edale CofE Primary School | Friends of Hope and Edale Schools (FOHES) (1083091) | postcode-exact S337ZD |
| St Joseph's Catholic Primary School | THE FRIENDS OF ST. JOSEPH'S SCHOOL CHALFONT ST. PETER (1069943) | postcode-exact SL98SB; domain stjosephschalfont.school (email) |
| Stow-on-the-Wold Primary School | STOW PTFA (1110850) | postcode-exact GL541AW |
| St John Fisher Catholic Primary School, Littlemore | FRIENDS OF ST JOHN FISHER PARENT TEACHER FRIENDS ASSOCIATION (PTFA) (1215950) | postcode-exact OX46LD |
| Orion Mead Road | FRIENDS OF MEAD ROAD SCHOOL (1182880) | postcode-exact BR76AD |
| Kettleshulme St James CofE (VA) Primary School | Kettleshulme School Parent Teacher and Friends Association (1105103) | postcode-exact SK237QU; domain kettleshulmestjames.cheshire.sch.uk (email) |
| Christ Church Cep Academy, Folkestone | CHRIST CHURCH CEP SCHOOL PARENT TEACHER AND FRIENDS ASSOCIATION (290502) | postcode-exact CT201DJ |

## 25 random `domain` matches for review

| school | charity | evidence |
|---|---|---|
| Redcliffe Childrens Centre and Maintained Nursery School | REDCLIFFE EARLY YEARS CENTRE PTA (1105280) | domain redcliffenurseryschool.co.uk (website) |
| Grappenhall St Wilfrid's CofE Primary School | THE FRIENDS OF ST WILFRIDS SCHOOL (1122140) | domain stwilfridsprimary.co.uk (website) |
| West London Free School Primary | West London and Earls Court Free School Primaries PTA (1159396) | domain wlfs-primary.org (website) |
| Kehelland Village School | KEHELLAND PARENT TEACHER STUDENT COMMUNITY ASSOCIATION (1220008) | domain kehellandschool.co.uk (website) |
| John Stainer Community Primary School | FRIENDS OF JOHN STAINER PTA (1104913) | domain johnstainer.lewisham.sch.uk (email); council-unique in Lewisham; address-town 'London' unique in Lewisham |
| Convent of Jesus and Mary RC Infant School | THE FEDERATION PARENTS STAFF FRIENDS ASSOCIATION (1218411) | domain cjminfantschool.co.uk (website) |
| Hullavington CofE Primary and Nursery School | Friends of Hullavington School (1074338) | domain hullavington.wilts.sch.uk (email); council-unique in Wiltshire; objects name 'hullavington primary school'; address-town 'Chippenham' unique in Wiltshire |
| St Nicholas CEVC Primary School | ST NICHOLAS C OF E PRIMARY SCHOOL PTFA (STROOD) (1110554) | domain st-nicholas.medway.sch.uk (email) |
| Signhills Infant Academy | SIGNHILLS HOME SCHOOL ASSOCIATION (1018579) | domain signhillsinfants.co.uk (email) |
| West End Primary School | PARENT TEACHER ASSOCIATION (1194259) | domain westend.lancs.sch.uk (email) |
| Bamber Bridge St Aidan's Church of England Primary School | ST AIDAN'S CE PRIMARY SCHOOL PTA (1094470) | domain staidansprimaryschool.co.uk (website) |
| St Patrick's Catholic Primary Academy | PARENTS AND FRIENDS ASSOCIATION OF ST PATRICK'S PRIMARY SCHOOL BIRSTALL (1032453) | domain stpatricksbirstall.co.uk (website) |
| Whitefield School | THE FRIENDS OF WHITEFIELD SCHOOLS (267817) | domain whitefield.org.uk (email); council-unique in Waltham Forest; objects name 'whitefield school' |
| Widcombe Infant School | WIDCOMBE SCHOOLS PTA (1143206) | domain widcombejuniorschool.com (website); council-unique in Bath and North East Somerset; address-town 'Bath' unique in Bath and North East Somerset |
| Harris Primary Academy Beckenham Green | BROMLEY ROAD PARENT TEACHER ASSOCIATION (1023475) | domain harrisbeckenhamgreen.org.uk (email); predecessor 'Bromley Road Primary School' unique in council area |
| Holy Trinity CofE Primary School, Lower Beeding | HOLY TRINITY C.E.P. SCHOOL PARENT TEACHER ASSOCIATON (1098901) | domain htlb.school (website) |
| St John's RC Primary School, a Voluntary Academy | ST JOHN'S RC PRIMARY SCHOOL PTA CHORLTON (1166215) | domain stjohnsrc.net (website) |
| Broadhempston Village Primary School | BROADHEMPSTON SCHOOL PARENT TEACHER AND FRIENDS ASSOCIATION (1101091) | domain broadhempston-primary.devon.sch.uk (website) |
| Avonmore Primary School | AVONMORE SCHOOL ASSOCIATION (1184757) | domain avonmoreprimary.co.uk (email); address-town 'London' unique in Hammersmith and Fulham |
| Brixham Church of England Primary School | Brixham C of E PTFA (1076732) | domain brixhamcofe.org (email) |
| Waterfoot Primary School | WATERFOOT PRIMARY PTA (1097208) | domain waterfoot.lancs.sch.uk (email); council-unique in Lancashire; address-town 'Rossendale' unique in Lancashire |
| Fred Nicholson School | FRIENDS OF FRED NICHOLSON SCHOOL (1062346) | domain frednicholson.norfolk.sch.uk (email); council-unique in Norfolk |
| St Anne's CofE Lydgate Primary School | ST ANNE'S PARENT TEACHER ASSOCIATION SADDLEWORTH (1102800) | domain stannescelydgate.oldham.sch.uk (email) |
| St John's Church of England Academy | THE ST JOHN'S CHURCH OF ENGLAND PRIMARY SCHOOL PARENTS' ASSOCIATION (1064791) | domain stjohns.covmat.org (email); council-unique in Coventry; address-town 'Coventry' unique in Coventry |
| Brant Broughton Church of England and Methodist Primary School | BRANT BROUGHTON PTA (1087316) | domain brant-broughton.lincs.sch.uk (website) |

## 25 random `predecessor` matches for review

| school | charity | evidence |
|---|---|---|
| Beacon View Primary School | FRIENDS OF THE GROVE INFANTS (1041513) | predecessor 'Grove Primary School' unique in council area |
| Highfield Farm Primary School | WEST MELTON PRIMARY SCHOOL PTA (1116765) | predecessor 'West Melton Primary School' unique in council area |
| Walton Oak Primary School | SWANSMERE SCHOOL PARENT TEACHER ASSOCIATION (1032238) | predecessor 'Swansmere School' unique in council area |
| Mulberry Academy St Leonards | FILSHAM VALLEY SCHOOL PARENTS TEACHERS AND FRIENDS ASSOCIATION (1053901) | predecessor 'Filsham Valley School' unique in council area |
| Danebury School | TEST VALLEY PARENT TEACHER ASSOCIATION (1102251) | predecessor 'Test Valley School' unique in council area |
| Churchill Park Complex Needs School | THE FRIENDS OF ALDERMAN JACKSON SCHOOL (292208) | predecessor 'Alderman Jackson School' unique in council area |
| West Fen Primary School | NEW YORK PRIMARY PTA (1103906) | predecessor 'New York Primary School' unique in council area |
| The Orchard Way Academy | THE PTA OF LANE END PRIMARY SCHOOL (1126693) | predecessor 'Lane End Primary School' unique in council area |
| Ormiston Cliff Park Primary Academy | FRIENDS OF CLIFF PARK MIDDLE SCHOOL (1046336) | predecessor 'Cliff Park Junior School' unique in council area |
| Richard Rose Central Academy | NORTH CUMBRIA TECHNOLOGY COLLEGE PARENT TEACHER ASSOCIATION (1072050) | predecessor 'North Cumbria Technology College' unique in council area |
| Wyre Forest School | BLAKEBROOK SCHOOL; PARENTS, TEACHERS AND FRIENDS ASSOCIATION (1068588) | predecessor 'Blakebrook School' unique in council area |
| Orion Blenheim | THE FRIENDS OF BLENHEIM PRIMARY SCHOOL (1093366) | predecessor 'Blenheim Primary School' unique in council area |
| University Academy Holbeach | THE FRIENDS OF ST GUTHLAC SCHOOL (1107770) | predecessor 'The St Guthlac School' unique in council area |
| Landau Forte Academy Greenacres | GREENACRES PARENT TEACHER ASSOCIATION (1142989) | predecessor 'Greenacres Primary School' unique in council area |
| Hebburn Lakes Primary School | FRIENDS OF LUKES LANE SCHOOL (1119392) | predecessor 'Lukes Lane Community School' unique in council area |
| Hallgate Primary School Cottingham | FRIENDS OF HALLGATE PRIMARY SCHOOL (1007790) | predecessor 'Hallgate Junior School' unique in council area |
| Co-op Academy Swinton | THE SWINTON HIGH SCHOOL PARENTS TEACHERS & FRIENDS ASSOCIATION (1097915) | predecessor 'The Swinton High School' unique in council area |
| Heron Park Primary Academy | HAMPDEN PARK INFANT SCHOOL PARENTS AND FRIENDS ASSOCIATION (1065956) | predecessor 'Hampden Park Infant School' unique in council area |
| Orchard Primary Academy | FRIENDS OF CHICKENLEY SCHOOL (1092815) | predecessor 'Chickenley Community Junior Infant and Nursery School' unique in council area |
| St John's Church of England Primary School | THE FRIENDS OF THE REDLANDS SCHOOLS (1048358) | predecessor 'The Redlands Junior School' unique in council area |
| Bedlington Academy | THE PARENT TEACHER ASSOCIATION OF BEDLINGTONSHIRE COMMUNITY HIGH SCHOOL (1061727) | predecessor 'Bedlingtonshire Community High School' unique in council area |
| St Matthew's Church of England Primary Academy | MIDDLETON FRIENDS OF THE SCHOOL ASSOCIATION (1046337) | predecessor 'Middleton Church of England Primary Academy' unique in council area |
| Hill Park School | FRIENDS OF DOWNS PARK SCHOOL (1036417) | predecessor 'Downs Park School' unique in council area |
| St Mary's Primary School, A Catholic Voluntary Academy | ST MARY'S CATHOLIC SCHOOL PTA, HIGH GREEN, SHEFFIELD (1113412) | predecessor 'St Mary's Catholic Primary School High Green' unique in council area |
| St. Joseph's Infant School | FRIENDS OF LANCASTRIAN INFANTS SCHOOL (1114423) | predecessor 'Lancastrian Infant School' unique in council area |

## 25 random `council-unique` matches for review

| school | charity | evidence |
|---|---|---|
| Oliver Tomkins Church of England Infant and Nursery School | FRIENDS OF OLIVER TOMKINS SCHOOLS (1060740) | council-unique in Swindon |
| Hollington Primary School | THE FRIENDS OF HOLLINGTON PRIMARY SCHOOL (1112288) | council-unique in East Sussex |
| Bishop Winnington-Ingram CofE Primary School | THE PARENTS ASSOCIATION OF BISHOPS WINNINGTON-INGRAM SCHOOL (1030859) | council-unique in Hillingdon |
| St John the Baptist Voluntary Aided Church of England Primary School | ST JOHN THE BAPTIST SCHOOL PTA (1030413) | council-unique in Hertfordshire |
| Harrington Junior School | HARRINGTON JUNIOR SCHOOL PARENT TEACHER ASSOCIATION (1013670) | council-unique in Derbyshire |
| Ardleigh Green Infant School | FRIENDS OF ARDLEIGH GREEN SCHOOLS (1014958) | council-unique in Havering, Essex |
| Ansford Academy | THE FRIENDS OF ANSFORD COMMUNITY SCHOOL (276752) | council-unique in Somerset; objects name 'ansford school' |
| Billingham South Community Primary School | BILLINGHAM SOUTH HOME SCHOOL ASSOCIATION (1039654) | council-unique in Stockton-on-Tees |
| Birdlip Primary School | BIRDLIP SCHOOL ASSOCIATION (1099884) | council-unique in Gloucestershire |
| Merton Abbey Primary School | THE FRIENDS OF MERTON ABBEY SCHOOL (297843) | council-unique in Merton |
| The Sir John Colfox Academy | SIR JOHN COLFOX SCHOOL PARENTS AND FRIENDS ASSOCIATION (270267) | council-unique in Dorset, Bournemouth, Christchurch and Poole |
| Upton Priory School | FRIENDS OF UPTON PRIORY INFANT SCHOOL (1044669) | council-unique in Cheshire East, Cheshire West and Chester |
| Barnwell Academy | FRIENDS OF BARNWELL SCHOOL (1110980) | council-unique in Sunderland |
| Elmbridge Primary School | THE FRIENDS OF ELMBRIDGE INFANTS SCHOOL (1014563) | council-unique in Gloucestershire; objects name 'elmbridge infant school' |
| Leagrave Primary School | LEAGRAVE PRIMARY SCHOOL PARENTS' ASSOCIATION (1044095) | council-unique in Luton |
| The Wavell School | WAVELL SCHOOL PARENT TEACHER ASSOCIATION (1038034) | council-unique in Hampshire |
| Luddenden CofE School | THE FRIENDS OF LUDDENDEN DENE SCHOOL (1042335) | council-unique in Calderdale |
| The Folkestone School for Girls | FRIENDS OF FOLKESTONE SCHOOL FOR GIRLS (294340) | council-unique in Kent |
| Leedstown Community Primary School | FRIENDS OF LEEDSTOWN SCHOOL (1016239) | council-unique in Cornwall |
| Teign School | FRIENDS OF TEIGN SCHOOL (1065725) | council-unique in Devon |
| Archbishop Cranmer Church of England Academy | FRIENDS OF ARCHBISHOP CRANMER SCHOOL (1045984) | council-unique in Nottinghamshire |
| Tanners Brook Primary School | FRIENDS OF TANNERS BROOK JUNIOR SCHOOL (1111281) | council-unique in Southampton |
| Lytchett Minster School | LYTCHETT MINSTER SCHOOL PARENT/TEACHER ASSOCIATION (1006454) | council-unique in Dorset, Bournemouth, Christchurch and Poole |
| Dame Janet Primary Academy | THE FRIENDS OF DAME JANET INFANTS SCHOOL (1001664) | council-unique in Kent |
| Prettygate Infant School | FRIENDS OF PRETTYGATE SCHOOLS (1199207) | council-unique in Essex; address-town 'Colchester' unique in Essex |

## 20 random `objects` matches for review

| school | charity | evidence |
|---|---|---|
| Acle Academy | ACLE ACADEMY PTA (281434) | objects name 'acle high school' |
| Howden School | PARENT TEACHER FRIENDS ASSOCIATION OF HOWDEN SCHOOL (1000385) | objects name 'howden secondary school' |
| Stimpson Avenue Academy | HELPING HANDS FRIENDS OF STIMPSON AVENUE ACADEMY (1011571) | objects name 'stimpson avenue lower school' |
| Kings Cliffe Endowed Primary School | OUNDLE & KINGS CLIFFE MIDDLE SCHOOL PFA - KINGS CLIFFE SITE (1096986) | objects name 'king cliffe middle school' |
| Rotherhithe Primary School | ROTHERHITHE PARENT TEACHER LINK (1018949) | objects name 'rotherhithe primary school' |
| Hiltingbury Junior School | HILTINGBURY SCHOOLS PARENT TEACHER ASSOCIATION (HSPTA) (288984) | objects name 'hiltingbury junior school' |
| Wincanton Primary School | PARENTS AND FRIENDS OF THE SCHOOL (1103324) | objects name 'wincanton primary school' |
| The Calder Learning Trust | CALDER HIGH SCHOOL PARENTS' NETWORK (1116402) | objects name 'calder high school' |
| The Topsham School | FRIENDS OF LITTLE ACORNS AT THE TOPSHAM SCHOOL (1123331) | objects name 'topsham school' |
| Abbeywood Community School | FRIENDS OF ABBEYWOOD COMMUNITY SCHOOL ENRICHMENT FUND (278226) | objects name 'abbeywood community school' |
| Hiltingbury Infant School | HILTINGBURY SCHOOLS PARENT TEACHER ASSOCIATION (HSPTA) (288984) | objects name 'hiltingbury junior school' |
| Fairfield School | FRIENDS OF FAIRFIELD SCHOOL (BATLEY) (1136776) | objects name 'fairfield school' |
| Flamstead Village School | FRIENDS OF FLAMSTEAD SCHOOL (1108572) | objects name 'flamstead village school' |
| Sandgate School | FAMILY AND FRIENDS OF SANDGATE SCHOOL (1084131) | objects name 'sandgate school' |
| Rode Methodist VC First School | FRIENDS OF RODE AND NORTON SCHOOLS (1070284) | objects name 'rode methodist vc first school' |
| The Ashbeach Primary School | FRIENDS OF ASHBEACH SCHOOL IN THE COUNTY OC CAMBRIDGESHIRE (1109246) | objects name 'ashbeach school' |
| Everest Community Academy | THE JOHN HUNT OF EVEREST PARENT TEACHERS ASSOCIATION (1043212) | objects name 'everest school' |
| Reckleford Infant School and Nursery | FRIENDS OF RECKLEFORD COMMUNITY SCHOOL AND CHILDREN'S CENTRE (1119270) | objects name 'reckleford community school' |
| Portfield School | FRIENDS OF PORTFIELD SCHOOL FOR AUTISTIC CHILDREN (262877) | objects name 'portfield school' |
| Queen Elizabeth High School | QUEEN ELIZABETH HUMANITIES COLLEGE PFA (1098051) | objects name 'queen elizabeth high school' |

## 16 random `address-town` matches for review

| school | charity | evidence |
|---|---|---|
| Cunningham Hill Junior School | CUNNINGHAM HILL SCHOOLS PTA (1194340) | address-town 'St Albans' unique in Hertfordshire |
| Cuxton Community Junior School | CUXTON SCHOOLS PTFA (1204185) | address-town 'Rochester' unique in Medway |
| Cunningham Hill Infant School | CUNNINGHAM HILL SCHOOLS PTA (1194340) | address-town 'St Albans' unique in Hertfordshire |
| William Martin Church of England Junior School | FRIENDS OF WILLIAM MARTIN PTA (1205801) | address-town 'Harlow' unique in Essex |
| Garden Suburb Infant School | GARDEN SUBURB SCHOOL PARENT TEACHER TRUST (288398) | address-town 'London' unique in Barnet |
| Maidstone, St Michael's Church of England Junior School | ST MICHAEL'S MAIDSTONE PTFA (1183459) | address-town 'Maidstone' unique in Kent |
| St Elphege's RC Junior School | ST ELPHEGE'S PTFA (1173387) | address-town 'Wallington' unique in Sutton |
| Joseph Rowntree School | FRIENDS OF JOSEPH ROWNTREE SCHOOL (1049046) | address-town 'York' unique in York |
| St Elphege's RC Infants' School | ST ELPHEGE'S PTFA (1173387) | address-town 'Wallington' unique in Sutton |
| Cuxton Community Infant School | CUXTON SCHOOLS PTFA (1204185) | address-town 'Rochester' unique in Medway |
| Garden Suburb Junior School | GARDEN SUBURB SCHOOL PARENT TEACHER TRUST (288398) | address-town 'London' unique in Barnet |
| Mickleover Primary School | FRIENDS OF MICKLEOVER PRIMARY SCHOOL ASSOCIATION (1066771) | address-town 'Derby' unique in Derby |
| St Michael's Church of England Infant School Maidstone | ST MICHAEL'S MAIDSTONE PTFA (1183459) | address-town 'Maidstone' unique in Kent |
| Coombe Boys' School | COOMBE BOYS' PARENT FRIENDS ASSOCIATION (1103700) | address-town 'New Malden' unique in Kingston upon Thames |
| Greenwood Primary and Nursery School | FRIENDS OF GREENWOOD INFANT AND NURSERY SCHOOL (F.O.G.I.N.S.) (1081801) | address-town 'Nottingham' unique in Nottinghamshire |
| William Martin Church of England Infant and Nursery School | FRIENDS OF WILLIAM MARTIN PTA (1205801) | address-town 'Harlow' unique in Essex |

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
