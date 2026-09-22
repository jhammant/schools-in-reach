<?php
/**
 * Plugin Name: Schools in Reach – nearby schools for property listings
 * Description: Nearby schools and Ofsted information, with admissions chances for subscribed agents. Automatic Property Hive integration or a shortcode for any theme.
 * Version: 1.0.0
 * Author: Hammant Labs
 * Author URI: https://www.schoolsinreach.com/agents/
 * Requires at least: 6.3
 * Requires PHP: 7.4
 * License: GPLv2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: schools-in-reach
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

function sir_defaults() {
    return array(
        'agent' => '',
        'phase' => 'both',
        'auto_insert' => 1,
        'position' => 'after-description',
        'departments' => array( 'residential-sales', 'residential-lettings' ),
        'heading' => '', // The widget titles itself; this adds an optional theme heading above it.
    );
}

function sir_text( $value ) {
    return is_scalar( $value ) ? (string) $value : '';
}

function sir_agent_id( $value ) {
    return substr( preg_replace( '/[^a-z0-9-]/', '', strtolower( sir_text( $value ) ) ), 0, 64 );
}

function sir_sanitize_settings( $input ) {
    $input = is_array( $input ) ? $input : array();
    $defaults = sir_defaults();
    return array(
        'agent' => sir_agent_id( $input['agent'] ?? '' ),
        'phase' => in_array( $input['phase'] ?? '', array( 'both', 'primary', 'secondary' ), true ) ? $input['phase'] : 'both',
        'auto_insert' => isset( $input['auto_insert'] ) && '1' === sir_text( $input['auto_insert'] ) ? 1 : 0,
        'position' => in_array( $input['position'] ?? '', array( 'after-features', 'after-summary', 'after-description' ), true ) ? $input['position'] : 'after-description',
        'departments' => array_values( array_intersect( $defaults['departments'], array_filter( (array) ( $input['departments'] ?? array() ), 'is_string' ) ) ),
        'heading' => sanitize_text_field( sir_text( $input['heading'] ?? $defaults['heading'] ) ),
    );
}

function sir_settings() {
    $stored = get_option( 'sir_settings', array() );
    return sir_sanitize_settings( array_merge( sir_defaults(), is_array( $stored ) ? $stored : array() ) );
}

/** Validate syntax, not postcode existence. The hosted widget performs the lookup. */
function sir_normalise_postcode( $postcode ) {
    $postcode = strtoupper( trim( sir_text( $postcode ) ) );
    $pattern = '/^(GIR\s*0AA|(?:[A-PR-UWYZ][0-9][0-9]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9]?|[A-PR-UWYZ][0-9][A-HJKPSTUW]|[A-PR-UWYZ][A-HK-Y][0-9][ABEHMNPRVWXY])\s*[0-9][ABD-HJLNP-UW-Z]{2})$/D';
    if ( ! preg_match( $pattern, $postcode ) ) {
        return '';
    }
    $postcode = preg_replace( '/\s+/', '', $postcode );
    return substr( $postcode, 0, -3 ) . ' ' . substr( $postcode, -3 );
}

/** Return escaped markup. Filters are trusted PHP extension points. */
function sir_render( $postcode, $args = array() ) {
    $args = array_merge( sir_settings(), is_array( $args ) ? $args : array() );
    $post_id = isset( $args['post_id'] ) ? absint( $args['post_id'] ) : get_the_ID();
    if ( ! apply_filters( 'sir_should_display', true, $post_id ) ) {
        return '';
    }
    $postcode = sir_normalise_postcode( apply_filters( 'sir_postcode', $postcode, $post_id ) );
    if ( '' === $postcode ) {
        return '';
    }
    $html = '<section class="sir-schools">';
    $heading = sir_text( $args['heading'] );
    if ( '' !== $heading ) {
        $html .= '<h2>' . esc_html( $heading ) . '</h2>';
    }
    $html .= '<div class="sir-widget" data-schools-in-reach data-postcode="' . esc_attr( $postcode ) . '"';
    $agent = sir_agent_id( $args['agent'] );
    if ( '' !== $agent ) {
        $html .= ' data-agent="' . esc_attr( $agent ) . '"';
    }
    if ( in_array( $args['phase'], array( 'primary', 'secondary' ), true ) ) {
        $html .= ' data-phase="' . esc_attr( $args['phase'] ) . '"';
    }
    $html .= '></div><noscript><a href="' . esc_url( 'https://www.schoolsinreach.com/embed/?postcode=' . rawurlencode( $postcode ) ) . '">' . esc_html__( 'See nearby schools', 'schools-in-reach' ) . '</a></noscript></section>';
    $html = apply_filters( 'sir_widget_html', $html, $post_id );
    if ( is_string( $html ) && '' !== $html ) {
        wp_enqueue_script( 'sir-widget', 'https://www.schoolsinreach.com/widget.js', array(), null, array( 'in_footer' => true, 'strategy' => 'async' ) );
        return $html;
    }
    return '';
}

function sir_is_property() {
    return function_exists( 'is_property' ) && is_property();
}

/** Read through PH_Property to preserve Property Hive's detail filters. */
function sir_property_detail( $key ) {
    global $property;
    if ( $property instanceof PH_Property && (int) $property->id === (int) get_queried_object_id() ) {
        return sir_text( $property->$key );
    }
    return sir_text( get_post_meta( get_queried_object_id(), '_' . $key, true ) );
}

function sir_property_allowed() {
    $settings = sir_settings();
    return sir_is_property()
        && in_array( sir_property_detail( 'address_country' ), array( '', 'GB' ), true )
        && in_array( sir_property_detail( 'department' ), $settings['departments'], true );
}

function sir_shortcode( $atts = array() ) {
    $settings = sir_settings();
    $atts = shortcode_atts( array(
        'postcode' => '',
        'phase' => $settings['phase'],
        'agent' => $settings['agent'],
        'heading' => $settings['heading'],
    ), $atts, 'schools_in_reach' );
    if ( sir_is_property() ) {
        if ( ! sir_property_allowed() ) {
            return '';
        }
        $atts['post_id'] = get_queried_object_id();
        if ( '' === $atts['postcode'] ) {
            $atts['postcode'] = sir_property_detail( 'address_postcode' );
        }
    }
    return sir_render( $atts['postcode'], $atts );
}

/** Inspect raw fields: formatting the description can execute shortcodes itself. */
function sir_property_has_shortcode( $post_id ) {
    if ( has_shortcode( (string) get_post_field( 'post_content', $post_id ), 'schools_in_reach' ) ) {
        return true;
    }
    foreach ( get_post_meta( $post_id ) as $key => $values ) {
        if ( preg_match( '/^_?(?:room_description_\d+|description_\d+|description|summary)$/', $key ) ) {
            foreach ( $values as $value ) {
                if ( is_string( $value ) && has_shortcode( $value, 'schools_in_reach' ) ) {
                    return true;
                }
            }
        }
    }
    return false;
}

function sir_auto_insert() {
    $settings = sir_settings();
    if ( ! $settings['auto_insert'] || ! sir_property_allowed() || sir_property_has_shortcode( get_queried_object_id() ) ) {
        return;
    }
    // Output is escaped by sir_render; sir_widget_html is a trusted HTML filter.
    echo sir_render( sir_property_detail( 'address_postcode' ), array( 'post_id' => get_queried_object_id() ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
}

function sir_init() {
    add_shortcode( 'schools_in_reach', 'sir_shortcode' );
    $settings = sir_settings();
    $priorities = array( 'after-features' => 25, 'after-summary' => 35, 'after-description' => 45 );
    add_action( 'propertyhive_after_single_property_summary', 'sir_auto_insert', $priorities[ $settings['position'] ] );
}
add_action( 'init', 'sir_init' );

function sir_admin_menu() {
    add_options_page( __( 'Schools in Reach', 'schools-in-reach' ), __( 'Schools in Reach', 'schools-in-reach' ), 'manage_options', 'schools-in-reach', 'sir_settings_page' );
}
add_action( 'admin_menu', 'sir_admin_menu' );

function sir_register_settings() {
    register_setting( 'sir_settings_group', 'sir_settings', array( 'type' => 'array', 'sanitize_callback' => 'sir_sanitize_settings', 'default' => sir_defaults() ) );
    add_settings_section( 'sir_main', '', '__return_false', 'schools-in-reach' );
    $labels = array(
        'agent' => __( 'Agent ID', 'schools-in-reach' ),
        'phase' => __( 'School phase', 'schools-in-reach' ),
        'auto_insert' => __( 'Property Hive auto-insert', 'schools-in-reach' ),
        'position' => __( 'Position', 'schools-in-reach' ),
        'departments' => __( 'Departments', 'schools-in-reach' ),
        'heading' => __( 'Heading', 'schools-in-reach' ),
    );
    foreach ( $labels as $key => $label ) {
        add_settings_field( 'sir_' . $key, $label, 'sir_settings_field', 'schools-in-reach', 'sir_main', array( 'key' => $key, 'label_for' => 'sir_' . $key ) );
    }
}
add_action( 'admin_init', 'sir_register_settings' );

function sir_settings_field( $args ) {
    $settings = sir_settings();
    $key = $args['key'];
    $name = 'sir_settings[' . $key . ']';
    if ( 'agent' === $key || 'heading' === $key ) {
        echo '<input type="text" class="regular-text" id="sir_' . esc_attr( $key ) . '" name="' . esc_attr( $name ) . '" value="' . esc_attr( $settings[ $key ] ) . '"' . ( 'agent' === $key ? ' maxlength="64"' : '' ) . '>';
        if ( 'agent' === $key ) {
            echo '<p class="description">' . esc_html__( 'Leave empty for the free preview: three nearest schools and Ofsted information.', 'schools-in-reach' ) . ' <a href="https://www.schoolsinreach.com/agents/#pricing">' . esc_html__( 'Start a 30-day free trial to unlock admissions chances', 'schools-in-reach' ) . '</a></p>';
        } else {
            echo '<p class="description">' . esc_html__( 'Optional heading above the widget, which already has its own title. Leave empty for none.', 'schools-in-reach' ) . '</p>';
        }
    } elseif ( 'auto_insert' === $key ) {
        echo '<label><input type="checkbox" id="sir_auto_insert" name="sir_settings[auto_insert]" value="1" ' . checked( $settings['auto_insert'], 1, false ) . '> ' . esc_html__( 'Automatically add to Property Hive property pages', 'schools-in-reach' ) . '</label><p class="description">';
        echo esc_html( class_exists( 'PH_Property' ) ? __( 'Property Hive detected ✓', 'schools-in-reach' ) : __( 'Property Hive not detected. Auto-insert only works when Property Hive is active; the shortcode works with any theme.', 'schools-in-reach' ) );
        echo '</p>';
    } elseif ( 'departments' === $key ) {
        foreach ( array( 'residential-sales' => __( 'Residential sales', 'schools-in-reach' ), 'residential-lettings' => __( 'Residential lettings', 'schools-in-reach' ) ) as $value => $label ) {
            echo '<label><input type="checkbox" name="sir_settings[departments][]" value="' . esc_attr( $value ) . '" ' . checked( in_array( $value, $settings['departments'], true ), true, false ) . '> ' . esc_html( $label ) . '</label><br>';
        }
        echo '<p class="description">' . esc_html__( 'Commercial properties are never included.', 'schools-in-reach' ) . '</p>';
    } else {
        $options = 'phase' === $key
            ? array( 'both' => __( 'Both', 'schools-in-reach' ), 'primary' => __( 'Primary', 'schools-in-reach' ), 'secondary' => __( 'Secondary', 'schools-in-reach' ) )
            : array( 'after-features' => __( 'After features', 'schools-in-reach' ), 'after-summary' => __( 'After summary', 'schools-in-reach' ), 'after-description' => __( 'After description', 'schools-in-reach' ) );
        echo '<select id="sir_' . esc_attr( $key ) . '" name="' . esc_attr( $name ) . '">';
        foreach ( $options as $value => $label ) {
            echo '<option value="' . esc_attr( $value ) . '" ' . selected( $settings[ $key ], $value, false ) . '>' . esc_html( $label ) . '</option>';
        }
        echo '</select>';
    }
}

function sir_settings_page() {
    if ( ! current_user_can( 'manage_options' ) ) {
        return;
    }
    echo '<div class="wrap"><h1>' . esc_html__( 'Schools in Reach', 'schools-in-reach' ) . '</h1>';
    echo '<p>' . esc_html__( 'The widget loads from schoolsinreach.com when a valid property postcode is rendered. It sends the postcode, agent ID (if set), selected phase and browser referrer origin to that service. The widget also looks up the postcode with api.postcodes.io.', 'schools-in-reach' ) . ' <a href="https://www.schoolsinreach.com/about.html">' . esc_html__( 'About the service and data', 'schools-in-reach' ) . '</a></p>';
    echo '<form action="options.php" method="post">';
    settings_fields( 'sir_settings_group' );
    do_settings_sections( 'schools-in-reach' );
    submit_button();
    echo '</form><p>' . esc_html__( 'For other WordPress themes, add [schools_in_reach postcode="E8 1DY"] in a Shortcode block. On a Property Hive property page, [schools_in_reach] uses that property’s postcode.', 'schools-in-reach' ) . '</p></div>';
}

function sir_plugin_links( $links ) {
    array_unshift( $links, '<a href="' . esc_url( admin_url( 'options-general.php?page=schools-in-reach' ) ) . '">' . esc_html__( 'Settings', 'schools-in-reach' ) . '</a>' );
    return $links;
}
add_filter( 'plugin_action_links_' . plugin_basename( __FILE__ ), 'sir_plugin_links' );
