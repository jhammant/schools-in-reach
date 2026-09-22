<?php
/** Offline contract tests: no WordPress install or network required. */
error_reporting( E_ALL );
set_error_handler( function ( $severity, $message, $file, $line ) {
    throw new ErrorException( $message, 0, $severity, $file, $line );
} );
define( 'ABSPATH', __DIR__ );
$GLOBALS['sir_test_options'] = array();
$GLOBALS['sir_test_hooks'] = array();
$GLOBALS['sir_test_scripts'] = array();
$GLOBALS['sir_test_meta'] = array();
$GLOBALS['sir_test_content'] = '';
$GLOBALS['sir_test_property'] = false;
$GLOBALS['sir_test_count'] = 0;
function __( $text, $domain = '' ) { return $text; }
function esc_attr( $text ) { return htmlspecialchars( (string) $text, ENT_QUOTES, 'UTF-8' ); }
function esc_html( $text ) { return esc_attr( $text ); }
function esc_html__( $text, $domain = '' ) { return esc_html( $text ); }
function esc_url( $text ) { return esc_attr( $text ); }
function sanitize_text_field( $text ) { return trim( strip_tags( $text ) ); }
function absint( $value ) { return abs( (int) $value ); }
function get_option( $key, $default = false ) { return $GLOBALS['sir_test_options'][ $key ] ?? $default; }
function delete_option( $key ) { unset( $GLOBALS['sir_test_options'][ $key ] ); }
function add_filter( $hook, $callback, $priority = 10, $args = 1 ) { $GLOBALS['sir_test_hooks'][ $hook ][ $priority ][] = array( $callback, $args ); }
function add_action( $hook, $callback, $priority = 10, $args = 1 ) { add_filter( $hook, $callback, $priority, $args ); }
function apply_filters( $hook, $value, ...$args ) {
    $hooks = $GLOBALS['sir_test_hooks'][ $hook ] ?? array();
    ksort( $hooks );
    foreach ( $hooks as $callbacks ) {
        foreach ( $callbacks as $entry ) { $value = call_user_func_array( $entry[0], array_slice( array_merge( array( $value ), $args ), 0, $entry[1] ) ); }
    }
    return $value;
}
function do_action( $hook ) {
    $hooks = $GLOBALS['sir_test_hooks'][ $hook ] ?? array();
    ksort( $hooks );
    foreach ( $hooks as $callbacks ) { foreach ( $callbacks as $entry ) { call_user_func( $entry[0] ); } }
}
function add_shortcode( $tag, $callback ) { $GLOBALS['sir_test_shortcodes'][ $tag ] = $callback; }
function shortcode_atts( $defaults, $atts, $tag = '' ) { return array_merge( $defaults, array_intersect_key( (array) $atts, $defaults ) ); }
function has_shortcode( $content, $tag ) { return (bool) preg_match( '/\[' . preg_quote( $tag, '/' ) . '(?:\s|\])/', $content ); }
function get_the_ID() { return 42; }
function get_queried_object_id() { return 42; }
function get_post_field( $field, $id ) { return $GLOBALS['sir_test_content']; }
function get_post_meta( $id, $key = '', $single = false ) {
    if ( '' === $key ) { return array_map( function ( $value ) { return array( $value ); }, $GLOBALS['sir_test_meta'] ); }
    return $GLOBALS['sir_test_meta'][ $key ] ?? '';
}
function wp_enqueue_script( $handle, $src = '', $deps = array(), $version = false, $args = array() ) { $GLOBALS['sir_test_scripts'][ $handle ] = compact( 'src', 'deps', 'version', 'args' ); }
function plugin_basename( $path ) { return basename( dirname( $path ) ) . '/' . basename( $path ); }
function admin_url( $path ) { return 'https://example.test/wp-admin/' . $path; }
function current_user_can( $cap ) { return $GLOBALS['sir_test_admin'] ?? true; }
function checked( $a, $b, $echo = true ) { return $a == $b ? 'checked="checked"' : ''; }
function selected( $a, $b, $echo = true ) { return $a == $b ? 'selected="selected"' : ''; }
function register_setting( $group, $key, $args ) { $GLOBALS['sir_test_registered'][ $key ] = $args; }
function add_settings_section( ...$args ) {}
function add_settings_field( $id, $label, $callback, $page, $section, $args ) { $GLOBALS['sir_test_fields'][] = array( $callback, $args ); }
function add_options_page( ...$args ) { $GLOBALS['sir_test_menu'] = $args; }
function settings_fields( $group ) { echo '<input name="_wpnonce" value="test">'; }
function do_settings_sections( $page ) { foreach ( $GLOBALS['sir_test_fields'] as $field ) { call_user_func( $field[0], $field[1] ); } }
function submit_button() { echo '<button>Save Changes</button>'; }
function sir_test( $condition, $message ) {
    ++$GLOBALS['sir_test_count'];
    if ( ! $condition ) { fwrite( STDERR, "FAIL: $message\n" ); exit( 1 ); }
}
function sir_capture( $callback ) { ob_start(); $callback(); return ob_get_clean(); }
require dirname( __DIR__ ) . '/schools-in-reach/schools-in-reach.php';
foreach ( array( 'E8 1DY' => 'E8 1DY', ' e8  1dy ' => 'E8 1DY', 'sw1a1aa' => 'SW1A 1AA', 'GIR 0AA' => 'GIR 0AA', 'gir0aa' => 'GIR 0AA', 'M1 1AE' => 'M1 1AE', 'B33 8TH' => 'B33 8TH', 'CR2 6XH' => 'CR2 6XH', 'DN55 1PT' => 'DN55 1PT', '' => '', 'invalid' => '', 'ZZ1 1AA' => '', 'E8 1CI' => '', 'E8 1DY<script>' => '', 'E 8 1DY' => '' ) as $input => $expected ) {
    sir_test( sir_normalise_postcode( $input ) === $expected, 'postcode: ' . $input );
}
sir_test( sir_normalise_postcode( array() ) === '', 'array postcode rejected' );
sir_test( sir_render( '' ) === '' && ! $GLOBALS['sir_test_scripts'], 'empty does not enqueue' );
sir_test( sir_render( 'bad' ) === '' && ! $GLOBALS['sir_test_scripts'], 'invalid does not enqueue' );
$html = sir_render( 'e81dy' );
sir_test( strpos( $html, 'data-postcode="E8 1DY"' ) !== false, 'normalised render' );
sir_test( strpos( $html, 'data-agent' ) === false, 'empty agent omitted' );
sir_test( strpos( $html, 'data-phase' ) === false, 'both phase omitted' );
sir_test( strpos( $html, '<h2>' ) === false, 'no heading by default (widget titles itself)' );
sir_test( strpos( sir_render( 'E8 1DY', array( 'heading' => 'Nearby schools' ) ), '<h2>Nearby schools</h2>' ) !== false, 'heading when set' );
sir_test( strpos( $html, 'https://www.schoolsinreach.com/embed/?postcode=E8%201DY' ) !== false, 'noscript URL' );
$script = $GLOBALS['sir_test_scripts']['sir-widget'];
sir_test( $script['src'] === 'https://www.schoolsinreach.com/widget.js' && $script['version'] === null && $script['args'] === array( 'in_footer' => true, 'strategy' => 'async' ), 'script contract' );
$html = sir_render( 'E8 1DY', array( 'agent' => 'a" onclick="evil', 'phase' => '"><script>', 'heading' => '<b>"Schools" & more</b>' ) );
sir_test( strpos( $html, 'onclick=' ) === false && strpos( $html, '<script>' ) === false && strpos( $html, '&lt;b&gt;&quot;Schools&quot; &amp; more&lt;/b&gt;' ) !== false, 'hostile attributes and heading safe' );
sir_test( strpos( sir_render( 'E8 1DY', array( 'heading' => '' ) ), '<h2>' ) === false, 'heading off' );
$GLOBALS['sir_test_options']['sir_settings'] = array_merge( sir_defaults(), array( 'agent' => 'stored', 'phase' => 'primary', 'heading' => 'Stored heading' ) );
do_action( 'init' );
sir_test( $GLOBALS['sir_test_shortcodes']['schools_in_reach'] === 'sir_shortcode', 'shortcode registered without PH' );
sir_test( ! function_exists( 'is_property' ), 'standalone mode has no Property Hive' );
$html = sir_shortcode( array( 'postcode' => 'w1a1aa', 'phase' => 'secondary', 'agent' => 'override', 'heading' => 'Override' ) );
sir_test( strpos( $html, 'data-postcode="W1A 1AA"' ) !== false && strpos( $html, 'data-phase="secondary"' ) !== false && strpos( $html, 'data-agent="override"' ) !== false && strpos( $html, '<h2>Override</h2>' ) !== false, 'shortcode overrides settings' );
$html = sir_shortcode( array( 'postcode' => 'E8 1DY', 'agent' => '', 'phase' => '', 'heading' => '' ) );
sir_test( strpos( $html, 'data-agent' ) === false && strpos( $html, 'data-phase' ) === false && strpos( $html, '<h2>' ) === false, 'explicit empty overrides' );
sir_test( sir_shortcode() === '', 'standalone requires postcode' );
$clean = sir_sanitize_settings( array( 'agent' => 'AB C_<"!123-', 'phase' => 'evil', 'position' => 'evil', 'departments' => array( 'commercial', 'residential-sales', array() ), 'heading' => '<b>Schools</b>' ) );
sir_test( $clean['agent'] === 'abc123-', 'agent sanitisation' );
sir_test( strlen( sir_agent_id( str_repeat( 'a', 90 ) ) ) === 64, 'agent max length' );
sir_test( $clean['phase'] === 'both' && $clean['position'] === 'after-description', 'whitelists' );
sir_test( $clean['departments'] === array( 'residential-sales' ), 'departments whitelist' );
sir_test( $clean['auto_insert'] === 0 && $clean['heading'] === 'Schools', 'unchecked auto and text heading' );
sir_test( sir_sanitize_settings( array() )['departments'] === array(), 'unchecked departments stay off' );
sir_test( sir_sanitize_settings( array( 'agent' => array(), 'phase' => array(), 'heading' => array() ) )['agent'] === '', 'malformed settings safe' );
foreach ( array( 'after-features' => 25, 'after-summary' => 35, 'after-description' => 45 ) as $position => $priority ) {
    unset( $GLOBALS['sir_test_hooks']['propertyhive_after_single_property_summary'] );
    $GLOBALS['sir_test_options']['sir_settings']['position'] = $position;
    sir_init();
    sir_test( isset( $GLOBALS['sir_test_hooks']['propertyhive_after_single_property_summary'][ $priority ] ), 'priority ' . $priority );
}
do_action( 'admin_init' );
do_action( 'admin_menu' );
sir_test( $GLOBALS['sir_test_registered']['sir_settings']['sanitize_callback'] === 'sir_sanitize_settings', 'Settings API sanitiser' );
sir_test( $GLOBALS['sir_test_menu'][2] === 'manage_options', 'admin menu capability' );
$html = sir_capture( 'sir_settings_page' );
sir_test( strpos( $html, 'Property Hive not detected' ) !== false && strpos( $html, 'Start a 30-day free trial' ) !== false && strpos( $html, '_wpnonce' ) !== false, 'standalone settings page' );
$GLOBALS['sir_test_admin'] = false;
sir_test( sir_capture( 'sir_settings_page' ) === '', 'settings capability guard' );
$GLOBALS['sir_test_admin'] = true;
sir_test( strpos( sir_plugin_links( array() )[0], 'options-general.php?page=schools-in-reach' ) !== false, 'plugin settings link' );
// Conditional declarations let the earlier tests run with no Property Hive installed.
if ( true ) {
    function is_property() { return $GLOBALS['sir_test_property']; }
    class PH_Property {
        public $id = 42;
        public function __get( $key ) { return get_post_meta( $this->id, '_' . $key, true ); }
    }
}
$GLOBALS['property'] = new PH_Property();
$GLOBALS['sir_test_property'] = true;
$GLOBALS['sir_test_options']['sir_settings'] = sir_defaults();
$GLOBALS['sir_test_meta'] = array( '_address_postcode' => 'e81dy', '_address_country' => 'GB', '_department' => 'residential-sales' );
sir_test( strpos( sir_capture( 'sir_auto_insert' ), 'E8 1DY' ) !== false, 'auto inserts sales' );
sir_test( strpos( sir_shortcode(), 'E8 1DY' ) !== false, 'shortcode property fallback' );
sir_test( strpos( sir_capture( 'sir_settings_page' ), 'Property Hive detected ✓' ) !== false, 'PH detection UI' );
$GLOBALS['sir_test_meta']['_department'] = 'commercial';
sir_test( sir_capture( 'sir_auto_insert' ) === '' && sir_shortcode( array( 'postcode' => 'E8 1DY' ) ) === '', 'commercial never shown' );
$GLOBALS['sir_test_meta']['_department'] = 'residential-lettings';
sir_test( sir_capture( 'sir_auto_insert' ) !== '', 'lettings default on' );
$GLOBALS['sir_test_options']['sir_settings']['departments'] = array( 'residential-sales' );
sir_test( sir_capture( 'sir_auto_insert' ) === '', 'respects department settings' );
$GLOBALS['sir_test_meta']['_department'] = 'residential-sales';
$GLOBALS['sir_test_meta']['_address_country'] = 'US';
sir_test( sir_capture( 'sir_auto_insert' ) === '' && sir_shortcode() === '', 'non GB excluded' );
$GLOBALS['sir_test_meta']['_address_country'] = '';
sir_test( sir_capture( 'sir_auto_insert' ) !== '', 'empty country permitted' );
$GLOBALS['sir_test_meta']['_address_postcode'] = 'invalid';
sir_test( sir_capture( 'sir_auto_insert' ) === '', 'invalid property postcode' );
add_filter( 'sir_postcode', function ( $value, $post_id ) { sir_test( $post_id === 42, 'postcode filter post ID' ); return 'SW1A 1AA'; }, 10, 2 );
sir_test( strpos( sir_capture( 'sir_auto_insert' ), 'SW1A 1AA' ) !== false, 'postcode filter before validation' );
unset( $GLOBALS['sir_test_hooks']['sir_postcode'] );
$GLOBALS['sir_test_meta']['_address_postcode'] = 'E8 1DY';
add_filter( 'sir_should_display', function ( $value, $post_id ) { sir_test( $post_id === 42, 'display filter post ID' ); return false; }, 10, 2 );
$GLOBALS['sir_test_scripts'] = array();
sir_test( sir_capture( 'sir_auto_insert' ) === '' && ! $GLOBALS['sir_test_scripts'], 'display filter suppresses auto and enqueue' );
unset( $GLOBALS['sir_test_hooks']['sir_should_display'] );
add_filter( 'sir_widget_html', function ( $html ) { return ''; } );
sir_test( sir_render( 'E8 1DY' ) === '' && ! $GLOBALS['sir_test_scripts'], 'empty final HTML does not enqueue' );
unset( $GLOBALS['sir_test_hooks']['sir_widget_html'] );
add_filter( 'sir_widget_html', function ( $html ) { return $html . '<!-- filtered -->'; } );
sir_test( strpos( sir_render( 'E8 1DY' ), '<!-- filtered -->' ) !== false, 'final HTML filter' );
unset( $GLOBALS['sir_test_hooks']['sir_widget_html'] );
$GLOBALS['sir_test_content'] = 'Before [schools_in_reach] after';
sir_test( sir_capture( 'sir_auto_insert' ) === '', 'post content duplicate skipped' );
$GLOBALS['sir_test_content'] = '';
foreach ( array( '_room_description_0', '_description_0', '_summary' ) as $key ) {
    $GLOBALS['sir_test_meta'][ $key ] = '[schools_in_reach phase="primary"]';
    sir_test( sir_capture( 'sir_auto_insert' ) === '', 'metadata duplicate: ' . $key );
    unset( $GLOBALS['sir_test_meta'][ $key ] );
}
$GLOBALS['sir_test_options']['sir_settings']['auto_insert'] = 0;
sir_test( sir_capture( 'sir_auto_insert' ) === '' && sir_shortcode() !== '', 'auto off preserves explicit shortcode' );
$GLOBALS['sir_test_options']['sir_settings']['auto_insert'] = 1;
$GLOBALS['sir_test_property'] = false;
sir_test( sir_capture( 'sir_auto_insert' ) === '', 'non property page excluded' );
define( 'WP_UNINSTALL_PLUGIN', true );
require dirname( __DIR__ ) . '/schools-in-reach/uninstall.php';
sir_test( ! isset( $GLOBALS['sir_test_options']['sir_settings'] ), 'uninstall removes settings' );
echo 'PASS: ' . $GLOBALS['sir_test_count'] . " assertions\n";
