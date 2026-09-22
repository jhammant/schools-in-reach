=== Schools in Reach – nearby schools for property listings ===
Contributors: hammantlabs
Tags: property, estate agent, schools, property hive, real estate
Requires at least: 6.3
Tested up to: 6.8
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Nearby schools on property listings. Automatic Property Hive integration, or a shortcode for any WordPress theme.

== Description ==

Help families explore schools near a property without leaving the listing. Schools in Reach embeds a responsive, automatically sized widget showing nearby primary and secondary schools, straight-line distances and Ofsted information. Each school links to its detailed Schools in Reach page.

No template editing is needed with Property Hive: activate the plugin and it adds the widget after the property description. Settings let you place it after features or summary instead, choose school phases and enable residential sales and/or residential lettings. Commercial and non-GB properties are excluded. A full, syntactically valid UK postcode is required.

Without an agent ID, the free preview shows the three nearest schools and Ofsted information. An active agent ID on an approved website domain unlocks the full widget, with up to five primary and five secondary schools and admissions chances where published data supports them. Unknown or inactive IDs and unapproved domains show the preview.

The service costs £29 per branch/month after a 30-day free trial. The first 20 founding agencies can use code FOUNDING for £19 per branch/month for the first 12 months. No VAT is charged. Cancel any time. See https://www.schoolsinreach.com/agents/#pricing for registration availability and details. The plugin itself is free; a subscription is optional.

School information covers England; admissions cut-off coverage is strongest in London. Historical offers are guidance, not a guarantee of admission. Distances use the postcode centre. Faith, siblings, ability bands and local admission rules may affect eligibility.

== Installation ==

1. In WordPress, open Plugins > Add New > Upload Plugin and select schools-in-reach-wordpress.zip.
2. Activate Schools in Reach.
3. Open Settings > Schools in Reach. Enter your agent ID if you have one, or leave it empty for the free preview.
4. With Property Hive active, view a residential property with a UK postcode. The widget appears automatically, provided your theme uses Property Hive's standard single-property hook.
5. Without Property Hive, add a Shortcode block containing [schools_in_reach postcode="E8 1DY"].

== Frequently Asked Questions ==

= Can I use this without Property Hive? =

Yes. Use a Shortcode block or a theme area that processes WordPress shortcodes:

[schools_in_reach postcode="E8 1DY"]
[schools_in_reach postcode="SW1A 1AA" phase="primary" agent="your-agent-id" heading="Local primary schools"]

On a Property Hive property page, [schools_in_reach] takes the current property's postcode. Attributes override saved settings. phase accepts both, primary or secondary; phase="" shows both. agent="" uses the free preview and heading="" hides the heading. A Custom HTML block does not reliably process shortcodes in all themes: use the Shortcode block for these examples.

= How do I avoid two widgets? =

Auto-insert skips properties whose post content or Property Hive description/room metadata already contains [schools_in_reach]. If your custom template places the shortcode elsewhere, disable auto-insert in settings. Property Hive description fields must be configured by your theme to process shortcodes if you place one there.

= Why is no widget shown? =

Check the full postcode, enabled departments, auto-insert setting and country (GB or empty). Commercial properties are never included. Custom Property Hive templates must fire propertyhive_after_single_property_summary. Other themes need an explicit postcode in the shortcode. Your theme must call wp_footer() for the loader to run. JavaScript is needed for the widget; a link is supplied when it is disabled. The plugin checks postcode syntax; the service checks whether the postcode exists.

= Why do I only see the preview? =

Check the agent ID and subscription status and have your website domain approved. Browser referrer restrictions can prevent domain verification. Please see https://www.schoolsinreach.com/agents/ for help.

= Does this replace Locrating? =

This is an independent alternative. It does not change Property Hive's Locrating settings. Disable that integration separately if you do not want both widgets. This plugin is not affiliated with Property Hive or Locrating.

= Can developers customise the output? =

sir_render( $postcode, $args ) returns widget markup; args accepts agent, phase, heading and post_id. The sir_postcode filter receives the postcode and post ID before validation. sir_should_display receives a boolean and post ID; return false to suppress output. sir_widget_html receives the final HTML and post ID. HTML filter callbacks are responsible for escaping any markup they add. Deleting the plugin removes sir_settings; deactivation preserves it.

== External services ==

This plugin relies on the Schools in Reach hosted service to display school information. When a valid postcode is rendered, the visitor's browser loads https://www.schoolsinreach.com/widget.js and an iframe at https://www.schoolsinreach.com/embed/. The iframe receives the property postcode, optional agent ID and selected school phase. The page's origin is sent via the iframe referrer under the strict-origin-when-cross-origin policy, for approved-domain verification. The initial script request follows your page's referrer policy. Normal web requests also expose the visitor's IP address and browser headers to the service.

Inside the iframe, the service requests the postcode from https://api.postcodes.io to obtain its coordinates, and loads school data and the agent registry from schoolsinreach.com. Postcodes.io receives the postcode and normal browser request information. These requests happen when visitors load a widget, not when saving settings. No WordPress account credentials or property owner's contact details are sent. The plugin makes no server-side external requests.

Service and data information: https://www.schoolsinreach.com/about.html
Subscription information: https://www.schoolsinreach.com/agents/
Postcode lookup service information: https://postcodes.io/

== Changelog ==

= 1.0.0 =
* Initial release: automatic Property Hive placement, settings, postcode validation, developer filters and standalone shortcode.
